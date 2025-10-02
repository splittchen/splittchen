"""Main routes for Splittchen application."""

from datetime import datetime as dt, timezone
from decimal import Decimal
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session, current_app, abort, Response
from typing import Optional, Tuple, Any
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app import db
from app.models import Group, Participant, Expense, ExpenseShare, KnownEmail
from app.forms import (CreateGroupForm, JoinGroupForm, AddParticipantForm, 
                      AddExpenseForm, EditExpenseForm, ShareGroupForm)
from app.utils import (send_group_invitation, send_group_creation_confirmation, 
                      calculate_settlements, format_currency, format_currency_suffix, get_participant_color, convert_expense_amount, setup_expense_form_choices, generate_history_text,
                      set_secure_admin_session, get_secure_admin_session, clear_all_group_sessions, execute_with_transaction)
from app.currency import currency_service

main = Blueprint('main', __name__)


def find_existing_participant_session(group: Any) -> Optional[Any]:
    """Check if user has an existing participant session that can be migrated to this group."""
    # Only check if there are any other participant sessions that might match by looking at session keys
    # This is for session migration only (same participant, different token format)
    for key, participant_id in session.items():
        if key.startswith('participant_') and isinstance(participant_id, int):
            participant = Participant.query.get(participant_id)
            if participant and participant.group_id == group.id:
                # This is session migration - same participant, different session key format
                # Only migrate if we don't already have a session for this group
                existing_key = f'participant_{group.share_token}'
                if existing_key not in session:
                    session[existing_key] = participant_id
                    current_app.logger.info(f"Migrated existing session for participant {participant.name} to group {group.name}")
                    return participant
    
    return None


def verify_participant_access(share_token: str, group_id: Optional[int] = None) -> Tuple[Optional[Any], Any]:
    """Verify participant has access to group. Returns (participant, group) or (None, group)."""
    # Allow access to inactive groups so users can view history and admins can manage
    group = Group.query.filter_by(share_token=share_token).first_or_404()
    
    if group_id and group.id != group_id:
        current_app.logger.warning(f"Group ID mismatch for token {share_token[:6]}...")
        return None, group
    
    # Check if user has admin access (grants full participant access)
    if session.get(f'admin_participant_{share_token}') or verify_admin_access(share_token, group):
        # Create a virtual admin participant for access
        class AdminParticipant:
            def __init__(self, group):
                self.id = 'admin'
                self.name = 'Admin'
                self.email = None
                self.group_id = group.id
                self.color = '#dc3545'  # Bootstrap danger color for admin
        
        current_app.logger.debug(f"Admin access granted for group {group.name}")
        return AdminParticipant(group), group
    
    participant_id = session.get(f'participant_{share_token}')
    if participant_id:
        participant = Participant.query.get(participant_id)
        if participant and participant.group_id == group.id:
            current_app.logger.debug(f"Participant {participant.name} verified for group {group.name}")
            return participant, group
        else:
            # Clear invalid session
            current_app.logger.warning(f"Invalid participant session for token {share_token[:6]}... - clearing session")
            session.pop(f'participant_{share_token}', None)
    
    # Try to find existing participant session
    participant = find_existing_participant_session(group)
    if participant:
        return participant, group
    
    # Check if user has viewer access via share token
    if session.get(f'viewer_{share_token}'):
        # Create a virtual viewer participant for access
        class ViewerParticipant:
            def __init__(self, group, share_token):
                self.id = 'viewer'
                # Get viewer email from session if available
                viewer_email = session.get(f'viewer_email_{share_token}')
                if viewer_email:
                    self.name = f"{viewer_email} (Guest)"
                    self.email = viewer_email
                else:
                    self.name = 'Anonymous Viewer'
                    self.email = None
                self.group_id = group.id
                self.color = '#6c757d'  # Bootstrap secondary color for viewer
        
        current_app.logger.debug(f"Viewer access granted for group {group.name}")
        return ViewerParticipant(group, share_token), group
    
    current_app.logger.debug(f"No participant session for token {share_token[:6]}...")
    return None, group


def verify_admin_access(share_token: str, group: Optional[Any] = None) -> bool:
    """Verify admin access to group using secure session.
    
    Args:
        share_token: Group share token
        group: Optional group object to avoid extra query
        
    Returns:
        bool: True if user has admin access
    """
    if group is None:
        group = Group.query.filter_by(share_token=share_token).first_or_404()
    
    admin_token = get_secure_admin_session(share_token)
    return admin_token == group.admin_token


@main.route('/')
def index() -> Any:
    """Homepage with create/join options and group history."""
    from .utils import get_user_groups_from_session
    user_groups = get_user_groups_from_session()
    return render_template('index.html', user_groups=user_groups)


@main.route('/p/<access_token>')
def participant_access(access_token: str) -> Any:
    """Direct participant access via unique token."""
    participant = Participant.query.filter_by(access_token=access_token).first()
    
    if not participant:
        flash('Invalid access link. Please check the link or contact the group admin.', 'error')
        return redirect(url_for('main.index'))
    
    group = participant.group
    if not group:
        flash('Group not found.', 'error')
        return redirect(url_for('main.index'))
    
    # Update last accessed timestamp
    participant.update_last_accessed()
    
    # Set participant session for this group
    session[f'participant_{group.share_token}'] = participant.id
    session.permanent = True  # Make session permanent for 90-day persistence
    
    current_app.logger.info(f"Participant {participant.name} accessed group '{group.name}' via personal link from IP {request.remote_addr}")
    
    # Redirect to group view
    return redirect(url_for('main.view_group', share_token=group.share_token))


@main.route('/create', methods=['GET', 'POST'])
def create_group() -> Any:
    """Create a new expense group."""
    form = CreateGroupForm()
    form.default_currency.choices = currency_service.get_currency_choices()
    
    # Set default currency from app config
    if request.method == 'GET':
        form.default_currency.data = current_app.config.get('DEFAULT_CURRENCY', 'USD')
    
    if form.validate_on_submit():
        # Retry group creation up to 3 times in case of token collision
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                # Create the group
                expires_at = None
                if form.expires_at.data:
                    # Convert date to datetime (end of day)
                    from datetime import time
                    expires_at = dt.combine(form.expires_at.data, time.max).replace(tzinfo=timezone.utc)
                
                group = Group(
                    name=form.group_name.data.strip() if form.group_name.data else '',
                    description=form.description.data.strip() if form.description.data else None,
                    expires_at=expires_at,
                    currency=form.default_currency.data,
                    is_recurring=form.is_recurring.data,
                    recurrence_type='monthly' if form.is_recurring.data else None,
                    creator_email=form.email.data.strip() if form.email.data else None
                )
                
                # Set next settlement date for recurring groups
                group.set_next_settlement_date()
                
                db.session.add(group)
                db.session.flush()  # Get group ID before adding participant
            
                # Add creator as first participant
                color = get_participant_color(0)  # First participant gets first color
                participant = Participant(
                    name=form.your_name.data.strip() if form.your_name.data else '',
                    email=form.email.data.strip() if form.email.data else None,
                    color=color,
                    group_id=group.id
                )
                db.session.add(participant)
                
                # Update known emails
                from app.utils import update_known_email
                update_known_email(participant.email, participant.name)
                
                db.session.commit()
                
                # Log successful group creation
                current_app.logger.info(f"New group '{group.name}' created by {participant.name} from IP {request.remote_addr}")
                
                # Store both admin and participant tokens in session with secure handling
                set_secure_admin_session(group.share_token, group.admin_token)
                session[f'participant_{group.share_token}'] = participant.id
                session.permanent = True  # Make session permanent for 90-day persistence
                
                # Send confirmation email to creator
                email_sent = send_group_creation_confirmation(
                    to_email=form.email.data.strip() if form.email.data else '',
                    group_name=group.name,
                    share_token=group.share_token,
                    admin_token=group.admin_token,
                    group_id=group.id
                )
                
                if email_sent:
                    flash(f'Welcome to "{group.name}"! Confirmation email sent to {form.email.data}', 'success')
                else:
                    flash(f'Welcome to "{group.name}"! (Email delivery failed, but your group is ready)', 'success')
                
                return redirect(url_for('main.view_group', share_token=group.share_token))
                
            except IntegrityError as e:
                db.session.rollback()
                current_app.logger.warning(f"Token collision detected (attempt {attempt + 1}/{max_attempts}): {e}")
                if attempt == max_attempts - 1:
                    # Last attempt failed, show error to user
                    flash('Error creating group due to system conflict. Please try again.', 'error')
                    break
                # Continue to next retry attempt
                continue
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"Unexpected error creating group: {e}")
                flash('Error creating group. Please try again.', 'error')
                break
    
    return render_template('create_group.html', form=form, 
                         system_default_currency=current_app.config.get('DEFAULT_CURRENCY', 'USD'))


@main.route('/group-created/<share_token>')
def group_created(share_token: str) -> Any:
    """Show group creation success page with sharing options."""
    group = Group.query.filter_by(share_token=share_token).first_or_404()
    
    # Verify admin access using secure session
    admin_token = get_secure_admin_session(share_token)
    if admin_token != group.admin_token:
        abort(403)
    
    base_url = current_app.config.get('BASE_URL', request.host_url.rstrip('/'))
    join_url = f'{base_url}/join/{share_token}'
    
    return render_template('group_created.html', group=group, join_url=join_url)


@main.route('/join/<share_token>')
def join_group_direct(share_token: str) -> Any:
    """Join group directly via link."""
    group = Group.query.filter_by(share_token=share_token, is_active=True).first()
    
    if not group:
        flash('Group not found or no longer active.', 'error')
        return redirect(url_for('main.index'))
    
    if group.is_expired or not group.is_active:
        abort(410)
    
    # Check if user is already a participant for this specific group
    participant_id = session.get(f'participant_{share_token}')
    if participant_id:
        participant = Participant.query.get(participant_id)
        if participant and participant.group_id == group.id:
            return redirect(url_for('main.view_group', share_token=share_token))
    
    # Handle settled groups - grant viewer access directly
    if group.is_settled:
        session[f'viewer_{share_token}'] = True
        
        # Store viewer email if available for better audit logging
        invite_email = request.args.get('email', '').strip()
        if invite_email:
            session[f'viewer_email_{share_token}'] = invite_email
        
        session.permanent = True  # Make session permanent for 90-day persistence
        return redirect(url_for('main.view_group', share_token=share_token))
    
    # For active groups, show the participant creation dialog
    # Create form for participant addition
    form = AddParticipantForm()
    
    # Pre-fill email if provided in URL parameter
    invite_email = request.args.get('email', '').strip()
    if invite_email and request.method == 'GET':
        form.email.data = invite_email
    
    return render_template('join_group.html', group=group, share_token=share_token, form=form, invite_email=invite_email)


@main.route('/join', methods=['GET', 'POST'])
def join_group() -> Any:
    """Join group via token input."""
    form = JoinGroupForm()
    
    if form.validate_on_submit():
        share_token = form.share_token.data.strip().upper() if form.share_token.data else ''
        return redirect(url_for('main.join_group_direct', share_token=share_token))
    
    return render_template('join_form.html', form=form)


@main.route('/add-participant/<share_token>', methods=['POST'])
def add_participant(share_token: str) -> Any:
    """Add participant to group."""
    group = Group.query.filter_by(share_token=share_token, is_active=True).first_or_404()
    
    if group.is_expired or group.is_settled or not group.is_active:
        abort(410)
    
    form = AddParticipantForm()
    
    # If form validation fails, show errors to user  
    if not form.validate_on_submit():
        for field_name, field_errors in form.errors.items():
            for error in field_errors:
                flash(f'{field_name}: {error}', 'error')
        return render_template('join_group.html', group=group, share_token=share_token, form=form)
    
    try:
        # Assign color based on current participant count
        color = get_participant_color(len(group.participants))
        
        participant = Participant(
            name=form.name.data.strip() if form.name.data else '',
            email=form.email.data.strip() if form.email.data else None,
            color=color,
            group_id=group.id
        )
        
        db.session.add(participant)
        db.session.commit()
        
        # Log the participant addition
        from app.utils import log_audit_action
        log_audit_action(
            group_id=group.id,
            action='participant_added',
            description=f'New participant joined: {participant.name}',
            performed_by=participant.name,
            performed_by_participant_id=participant.id,
            participant_id=participant.id,
            details={
                'participant_name': participant.name,
                'participant_email': participant.email,
                'participant_color': participant.color,
                'added_by_admin': False
            }
        )
        
        # Store participant in session
        session[f'participant_{share_token}'] = participant.id
        session.permanent = True  # Make session permanent for 90-day persistence
        
        # Log successful participant join
        current_app.logger.info(f"New participant {participant.name} joined group '{group.name}' from IP {request.remote_addr}")
        
        # Update known emails if provided
        from app.utils import update_known_email
        update_known_email(participant.email, participant.name)
        
        # Broadcast real-time update to all group members
        from app.socketio_events.group_events import broadcast_participant_joined
        broadcast_participant_joined(group.share_token, {
            'id': participant.id,
            'name': participant.name,
            'email': participant.email,
            'color': participant.color
        })
        
        flash(f'Welcome to "{group.name}", {participant.name}!', 'success')
        return redirect(url_for('main.view_group', share_token=share_token))
        
    except IntegrityError:
        db.session.rollback()
        flash('Error adding participant. Please try again.', 'error')
        return render_template('join_group.html', group=group, share_token=share_token, form=form)


@main.route('/group/<share_token>')
def view_group(share_token: str) -> Any:
    """View group expenses and balances."""
    # Check for participant access token in query parameter
    participant_token = request.args.get('p')
    if participant_token:
        participant = Participant.query.filter_by(access_token=participant_token).first()
        if participant and participant.group.share_token == share_token:
            # Set participant session and update last accessed
            session[f'participant_{share_token}'] = participant.id
            session.permanent = True
            participant.update_last_accessed()
            current_app.logger.info(f"Participant {participant.name} accessed group via query parameter from IP {request.remote_addr}")
    
    participant, group = verify_participant_access(share_token)
    
    # Add group to user's recent groups when accessed via link
    if group and group.is_active:
        # Store group access in session for recent groups display
        user_groups = session.get('user_groups', [])
        
        # Check if group is already in recent groups
        group_exists = any(g.get('share_token') == share_token for g in user_groups)
        
        if not group_exists:
            # Add to recent groups (limit to 10 most recent)
            from datetime import datetime
            user_groups.insert(0, {
                'share_token': share_token,
                'admin_token': group.admin_token,
                'accessed_at': datetime.utcnow().isoformat()
            })
            # Keep only the 10 most recent groups
            session['user_groups'] = user_groups[:10]
            current_app.logger.info(f"Added group '{group.name}' to user's recent groups")
    
    if not participant:
        # Grant viewer access for valid share tokens  
        if group and group.is_active:
            session[f'viewer_{share_token}'] = True
            session.permanent = True  # Make session permanent for 90-day persistence
            # Re-verify access now that viewer session is set
            participant, group = verify_participant_access(share_token)
        else:
            return redirect(url_for('main.join_group_direct', share_token=share_token))
    
    # Get expenses with eager loading for better performance
    # Show only non-archived expenses in main view
    expenses = (Expense.query.filter_by(group_id=group.id, is_archived=False)
                .options(joinedload(Expense.paid_by))
                .order_by(Expense.created_at.desc())
                .all())
    
    # Get all expenses (including archived) for history tab
    all_expenses = (Expense.query.filter_by(group_id=group.id)
                    .options(joinedload(Expense.paid_by))
                    .order_by(Expense.created_at.desc())
                    .all())
    
    # Get display currency from request or use group default
    display_currency = request.args.get('currency', group.currency)
    
    balances = group.get_balances(display_currency)
    settlements = calculate_settlements(balances)
    
    # Check if user is admin
    is_admin = verify_admin_access(share_token, group)
    
    # Get audit logs for history tab
    from app.models import AuditLog
    limit = current_app.config.get('ACTIVITY_LOG_LIMIT', 100)
    audit_logs = AuditLog.query.filter_by(group_id=group.id).order_by(AuditLog.created_at.desc()).limit(limit).all()
    
    return render_template('group.html', 
                         group=group, 
                         participant=participant,
                         expenses=expenses,
                         all_expenses=all_expenses,
                         balances=balances,
                         settlements=settlements,
                         participants=group.participants,
                         is_admin=is_admin,
                         audit_logs=audit_logs,
                         display_currency=display_currency,
                         currency_choices=currency_service.get_currency_choices(),
                         format_currency=format_currency,
                         format_currency_suffix=format_currency_suffix,
                         currency_service=currency_service)


@main.route('/group/<share_token>/add-expense', methods=['GET', 'POST'])
def add_expense(share_token):
    """Add expense to group."""
    participant, group = verify_participant_access(share_token)
    if not participant:
        return redirect(url_for('main.join_group_direct', share_token=share_token))
    
    if group.is_expired or group.is_settled or not group.is_active:
        abort(410)
    
    form = AddExpenseForm()
    setup_expense_form_choices(form, group)
    
    # Set default currency to group's default
    if request.method == 'GET':
        form.currency.data = group.currency
        form.date.data = dt.now(timezone.utc).date()
    
    if form.validate_on_submit():
        try:
            # Convert amount to base currency for calculations
            original_amount = form.amount.data
            currency = form.currency.data
            
            converted_amount, exchange_rate = convert_expense_amount(original_amount, currency, group)
            if converted_amount is None:
                flash(f'Unable to convert {currency} to {group.currency}. Please try again later.', 'error')
                return render_template('add_expense.html', form=form, group=group, participant=participant)
            
            expense = Expense(
                title=form.title.data.strip() if form.title.data else '',
                description=form.description.data.strip() if form.description.data else None,
                amount=float(converted_amount),  # Store converted amount
                currency=currency,
                original_amount=float(original_amount) if original_amount is not None else None,
                exchange_rate=float(exchange_rate) if exchange_rate is not None else 1.0,
                category=form.category.data,
                date=form.date.data,
                split_type=form.split_type.data,
                group_id=group.id,
                paid_by_id=form.paid_by_id.data
            )
            
            db.session.add(expense)
            db.session.flush()  # Get expense ID
            
            # Handle splits (currently only EQUAL is implemented)
            selected_participant_ids = form.split_between.data
            if not selected_participant_ids:
                selected_participant_ids = [p.id for p in group.participants]  # Default to all if none selected
            
            share_amount = expense.amount / len(selected_participant_ids)
            for participant_id in selected_participant_ids:
                share = ExpenseShare(
                    expense_id=expense.id,
                    participant_id=participant_id,
                    amount=round(share_amount, 2)  # Round to 2 decimal places
                )
                db.session.add(share)
            
            db.session.commit()
            
            # Log the expense creation
            from app.utils import log_audit_action
            log_audit_action(
                group_id=group.id,
                action='expense_added',
                description=f'Added expense "{expense.title}" (${expense.amount})',
                performed_by=participant.name,
                performed_by_participant_id=participant.id if isinstance(participant.id, int) else None,
                expense_id=expense.id,
                details={
                    'expense_title': expense.title,
                    'expense_amount': float(expense.amount),
                    'expense_currency': expense.currency,
                    'paid_by_name': expense.paid_by.name,
                    'split_count': len(expense.expense_shares)
                }
            )
            
            # Broadcast real-time expense update to all group members
            from app.socketio_events.group_events import broadcast_expense_added, broadcast_balance_updated
            broadcast_expense_added(group.share_token, {
                'id': expense.id,
                'title': expense.title,
                'amount': float(expense.amount),
                'currency': expense.currency,
                'date': expense.date.isoformat(),
                'category': expense.category,
                'split_type': expense.split_type,
                'paid_by': {
                    'id': expense.paid_by.id,
                    'name': expense.paid_by.name,
                    'color': expense.paid_by.color
                },
                'description': expense.description
            })
            
            # Also broadcast updated balances
            balances = group.get_balances()
            broadcast_balance_updated(group.share_token, {
                'balances': {str(p_id): {'amount': float(balance), 'currency': group.currency} 
                           for p_id, balance in balances.items()}
            })
            
            flash(f'Expense "{expense.title}" added successfully!', 'success')
            return redirect(url_for('main.view_group', share_token=share_token))
            
        except (IntegrityError, ValueError) as e:
            db.session.rollback()
            current_app.logger.error(f'Error adding expense: {e}')
            flash('Error adding expense. Please check your input and try again.', 'error')
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'Unexpected error adding expense: {e}')
            flash('An unexpected error occurred. Please try again.', 'error')
    
    return render_template('add_expense.html', form=form, group=group, participant=participant)


@main.route('/group/<share_token>/expense/<int:expense_id>/edit', methods=['GET', 'POST'])
def edit_expense(share_token, expense_id):
    """Edit an existing expense."""
    participant, group = verify_participant_access(share_token)
    if not participant:
        return redirect(url_for('main.join_group_direct', share_token=share_token))
    
    if group.is_expired or group.is_settled or not group.is_active:
        abort(410)
    
    # Get the expense and verify it belongs to this group
    expense = Expense.query.filter_by(id=expense_id, group_id=group.id).first_or_404()
    
    form = EditExpenseForm()
    setup_expense_form_choices(form, group)
    
    if request.method == 'GET':
        # Populate form with existing data
        form.title.data = expense.title
        form.description.data = expense.description
        form.amount.data = expense.original_amount
        form.currency.data = expense.currency
        form.category.data = expense.category
        form.paid_by_id.data = expense.paid_by_id
        form.split_type.data = expense.split_type
        form.date.data = expense.date.date() if expense.date else None
        # Set current participants who are splitting this expense
        form.split_between.data = [share.participant_id for share in expense.expense_shares]
    
    if form.validate_on_submit():
        try:
            # Convert amount to base currency for calculations
            original_amount = form.amount.data
            currency = form.currency.data
            
            converted_amount, exchange_rate = convert_expense_amount(original_amount, currency, group)
            if converted_amount is None:
                flash(f'Unable to convert {currency} to {group.currency}. Please try again later.', 'error')
                return render_template('edit_expense.html', form=form, group=group, participant=participant, expense=expense)
            
            # Update expense
            expense.title = form.title.data.strip() if form.title.data else ''
            expense.description = form.description.data.strip() if form.description.data else None
            expense.amount = converted_amount
            expense.currency = currency
            expense.original_amount = original_amount
            expense.exchange_rate = exchange_rate
            expense.category = form.category.data
            expense.date = form.date.data
            expense.split_type = form.split_type.data
            expense.paid_by_id = form.paid_by_id.data
            
            # Delete existing shares and recreate them
            ExpenseShare.query.filter_by(expense_id=expense.id).delete()
            
            # Handle splits (currently only EQUAL is implemented)
            selected_participant_ids = form.split_between.data
            if not selected_participant_ids:
                selected_participant_ids = [p.id for p in group.participants]  # Default to all if none selected
            
            share_amount = float(expense.amount) / len(selected_participant_ids)
            for participant_id in selected_participant_ids:
                share = ExpenseShare(
                    expense_id=expense.id,
                    participant_id=participant_id,
                    amount=round(share_amount, 2)  # Round to 2 decimal places
                )
                db.session.add(share)
            
            db.session.commit()
            
            # Log the expense update
            from app.utils import log_audit_action
            log_audit_action(
                group_id=group.id,
                action='expense_updated',
                description=f'Updated expense "{expense.title}" ({expense.currency}{expense.original_amount})',
                performed_by=participant.name,
                performed_by_participant_id=participant.id if isinstance(participant.id, int) else None,
                expense_id=expense.id,
                details={
                    'expense_title': expense.title,
                    'expense_amount': float(expense.amount),
                    'expense_currency': expense.currency,
                    'expense_category': expense.category,
                    'paid_by_name': expense.paid_by.name,
                    'split_count': len(expense.expense_shares)
                }
            )
            
            # Broadcast real-time update to all group members
            from app.socketio_events.group_events import broadcast_expense_updated, broadcast_balance_updated
            broadcast_expense_updated(group.share_token, {
                'id': expense.id,
                'title': expense.title,
                'amount': float(expense.amount),
                'currency': expense.currency,
                'date': expense.date.isoformat(),
                'category': expense.category,
                'split_type': expense.split_type,
                'paid_by': {
                    'id': expense.paid_by.id,
                    'name': expense.paid_by.name,
                    'color': expense.paid_by.color
                },
                'description': expense.description
            })
            
            # Also broadcast updated balances
            balances = group.get_balances()
            broadcast_balance_updated(group.share_token, {
                'balances': {str(p_id): {'amount': float(balance), 'currency': group.currency} 
                           for p_id, balance in balances.items()}
            })
            
            flash(f'Expense "{expense.title}" updated successfully!', 'success')
            return redirect(url_for('main.view_group', share_token=share_token))
            
        except (IntegrityError, ValueError) as e:
            db.session.rollback()
            current_app.logger.error(f'Error updating expense: {e}')
            flash('Error updating expense. Please check your input and try again.', 'error')
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'Unexpected error updating expense: {e}')
            flash('An unexpected error occurred. Please try again.', 'error')
    
    return render_template('edit_expense.html', form=form, group=group, participant=participant, expense=expense)


@main.route('/group/<share_token>/settle', methods=['POST'])
def settle_group(share_token):
    """Settle group and send final reports (admin only)."""
    group = Group.query.filter_by(share_token=share_token, is_active=True).first_or_404()
    
    # Check if user is admin
    is_admin = verify_admin_access(share_token, group)
    if not is_admin:
        current_app.logger.warning(f"Unauthorized settlement attempt for group {group.name} from IP {request.remote_addr}")
        abort(403)
    
    if group.is_expired or group.is_settled or not group.is_active:
        abort(410)
    
    def perform_settlement_database_operations():
        """Perform database operations for settlement in a transaction."""
        # Get balances before settling
        balances = group.get_balances(group.currency)
        settlements = calculate_settlements(balances)
        
        # Create settlement period entry for history tracking
        from datetime import date
        from app.models import SettlementPeriod
        
        today = date.today()
        period_name = f"{today.strftime('%Y-%m')}-FINAL"  # Mark as final settlement
        
        # Calculate total expenses (not archived)
        current_expenses = [exp for exp in group.expenses if not exp.is_archived]
        total_amount = sum(expense.amount for expense in current_expenses)
        
        settlement_period = SettlementPeriod(
            group_id=group.id,
            period_name=period_name,
            settled_at=dt.now(timezone.utc),
            total_amount=total_amount,
            participant_count=len(group.participants)
        )
        db.session.add(settlement_period)
        
        # Archive current expenses
        for expense in current_expenses:
            expense.settlement_period = period_name
            expense.is_archived = True
        
        # Mark group as settled
        group.is_settled = True
        group.settled_at = dt.now(timezone.utc)
        
        # Create audit log entry for final settlement
        from app.models import AuditLog
        audit_log = AuditLog(
            group_id=group.id,
            action='group_settled',
            description=f'Group settled and closed: {len(current_expenses)} expenses archived to period {period_name}.',
            details={
                'settlement_type': 'final_settlement',
                'period_name': period_name,
                'expenses_archived': len(current_expenses),
                'total_amount': float(total_amount),
                'participants_count': len(group.participants),
                'group_closed': True
            },
            performed_by='Admin'
        )
        db.session.add(audit_log)
        
        return {
            'balances': balances,
            'settlements': settlements,
            'period_name': period_name,
            'current_expenses': current_expenses
        }

    try:
        # Execute database operations in transaction
        settlement_data = execute_with_transaction(
            perform_settlement_database_operations,
            operation_description="group settlement database operations"
        )
        
        # Send final reports to all participants (outside transaction)
        from app.utils import send_final_settlement_report
        
        success_count = 0
        failed_reasons = []
        no_email_count = 0
        
        for participant in group.participants:
            if participant.email:
                success, message = send_final_settlement_report(
                    participant.email,
                    participant.name,
                    group.name,
                    settlement_data['balances'],
                    settlement_data['settlements'],
                    group.participants,
                    group.currency,
                    is_period_settlement=False,  # This is a final settlement
                    group_id=group.id,
                    participant_id=participant.id,
                    share_token=group.share_token
                )
                if success:
                    success_count += 1
                else:
                    failed_reasons.append(f"{participant.name}: {message}")
            else:
                no_email_count += 1
        
        # Update audit log with email statistics (separate transaction)
        def update_email_stats():
            from app.models import AuditLog
            audit_log = AuditLog.query.filter_by(
                group_id=group.id,
                action='group_settled'
            ).order_by(AuditLog.created_at.desc()).first()
            
            if audit_log and audit_log.details:
                audit_log.details['emails_sent'] = success_count
                audit_log.description = f'Group settled and closed: {len(settlement_data["current_expenses"])} expenses archived to period {settlement_data["period_name"]}. {success_count} email reports sent.'
        
        execute_with_transaction(
            update_email_stats,
            operation_description="settlement email statistics update"
        )
        
        # Create detailed flash messages
        total_participants = len(group.participants)
        
        if success_count == total_participants:
            flash(f'Group settled successfully! Final reports sent to all {success_count} participants.', 'success')
        elif success_count > 0:
            message_parts = [f'Group settled successfully! Final reports sent to {success_count}/{total_participants} participants.']
            if no_email_count > 0:
                message_parts.append(f'{no_email_count} participants have no email address.')
            if failed_reasons:
                message_parts.append('Some emails failed:')
                for reason in failed_reasons[:3]:  # Show max 3 detailed reasons
                    message_parts.append(f'• {reason}')
                if len(failed_reasons) > 3:
                    message_parts.append(f'• ... and {len(failed_reasons) - 3} more')
            flash(' '.join(message_parts), 'warning')
        else:
            message_parts = ['Group settled successfully! However, no email reports were sent.']
            if no_email_count > 0:
                message_parts.append(f'{no_email_count} participants have no email address.')
            if failed_reasons:
                message_parts.append('Email delivery failed:')
                for reason in failed_reasons[:3]:  # Show max 3 detailed reasons
                    message_parts.append(f'• {reason}')
                if len(failed_reasons) > 3:
                    message_parts.append(f'• ... and {len(failed_reasons) - 3} more')
            flash(' '.join(message_parts), 'warning')
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Error settling group: {e}')
        flash('Error settling group. Please try again.', 'error')
    
    return redirect(url_for('main.view_group', share_token=share_token))


@main.route('/group/<share_token>/settle-only', methods=['POST'])
def settle_only_group(share_token):
    """Send settlement reports without closing the group (admin only)."""
    group = Group.query.filter_by(share_token=share_token, is_active=True).first_or_404()
    
    # Check if user is admin
    is_admin = verify_admin_access(share_token, group)
    if not is_admin:
        abort(403)
    
    if group.is_expired:
        abort(410)
    
    try:
        # Get current balances and settlements
        balances = group.get_balances(group.currency)
        settlements = calculate_settlements(balances)
        
        # Check if there are any expenses or balances to settle
        current_expenses = [exp for exp in group.expenses if not exp.is_archived]
        if not current_expenses:
            flash('No current expenses to settle. Add some expenses first.', 'warning')
            return redirect(url_for('main.view_group', share_token=share_token))
        
        # Check if there are any non-zero balances
        has_balances = any(abs(balance) > 0.01 for balance in balances.values())
        if not has_balances:
            flash('All balances are already settled. No settlement report needed.', 'info')
            return redirect(url_for('main.view_group', share_token=share_token))
        
        from app.utils import send_final_settlement_report
        from datetime import date
        from app.models import SettlementPeriod
        
        # Create settlement period name (YYYY-MM format)
        today = date.today()
        period_name = today.strftime('%Y-%m')
        
        # Calculate total expenses for this period
        total_amount = sum(expense.amount for expense in current_expenses)
        
        # Create settlement period record - always create for settlement reports
        settlement_period = SettlementPeriod(
            group_id=group.id,
            period_name=period_name,
            settled_at=dt.now(timezone.utc),
            total_amount=total_amount,
            participant_count=len(group.participants)
        )
        db.session.add(settlement_period)
        
        # Archive current expenses - always archive when settling
        for expense in current_expenses:
            expense.settlement_period = period_name
            expense.is_archived = True
        
        # Update next settlement date for recurring groups
        if group.is_recurring:
            from datetime import time
            import calendar
            if today.month == 12:
                next_month_year = today.year + 1
                next_month = 1
            else:
                next_month_year = today.year
                next_month = today.month + 1
            
            last_day_next = calendar.monthrange(next_month_year, next_month)[1]
            next_settlement = date(next_month_year, next_month, last_day_next)
            settlement_time = time(hour=23, minute=59)
            group.next_settlement_date = dt.combine(next_settlement, settlement_time)

        # Send report to each participant
        success_count = 0
        failed_reasons = []
        no_email_count = 0
        
        for participant in group.participants:
            if participant.email:
                success, message = send_final_settlement_report(
                    participant.email,
                    participant.name,
                    group.name,
                    balances,
                    settlements,
                    group.participants,
                    group.currency,
                    is_period_settlement=True,  # Flag to indicate this is a period settlement
                    group_id=group.id,
                    participant_id=participant.id,
                    share_token=group.share_token
                )
                if success:
                    success_count += 1
                else:
                    failed_reasons.append(f"{participant.name}: {message}")
            else:
                no_email_count += 1
        
        # Create audit log entry for settlement
        from app.models import AuditLog
        audit_log = AuditLog(
            group_id=group.id,
            action='group_settled_period',
            description=f'Settlement completed: {len(current_expenses)} expenses archived to period {period_name}. {success_count} email reports sent.',
            details={
                'settlement_type': 'period_settlement',
                'period_name': period_name,
                'expenses_archived': len(current_expenses),
                'total_amount': float(total_amount),
                'participants_count': len(group.participants),
                'emails_sent': success_count,
                'is_recurring': group.is_recurring
            },
            performed_by='Admin'
        )
        db.session.add(audit_log)
        
        db.session.commit()
        
        # Create detailed flash messages
        total_participants = len(group.participants)
        
        if success_count == total_participants:
            flash(f'Balances settled and reports sent to all {success_count} participants. Expenses moved to history. Group remains open for new expenses.', 'success')
        elif success_count > 0:
            message_parts = [f'Balances settled! Reports sent to {success_count}/{total_participants} participants. Expenses moved to history. Group remains open.']
            if no_email_count > 0:
                message_parts.append(f'{no_email_count} participants have no email address.')
            if failed_reasons:
                message_parts.append('Some emails failed:')
                for reason in failed_reasons[:3]:  # Show max 3 detailed reasons
                    message_parts.append(f'• {reason}')
                if len(failed_reasons) > 3:
                    message_parts.append(f'• ... and {len(failed_reasons) - 3} more')
            flash(' '.join(message_parts), 'warning')
        else:
            message_parts = ['Balances settled and expenses moved to history. Group remains open. However, no email reports were sent.']
            if no_email_count > 0:
                message_parts.append(f'{no_email_count} participants have no email address.')
            if failed_reasons:
                message_parts.append('Email delivery failed:')
                for reason in failed_reasons[:3]:  # Show max 3 detailed reasons
                    message_parts.append(f'• {reason}')
                if len(failed_reasons) > 3:
                    message_parts.append(f'• ... and {len(failed_reasons) - 3} more')
            flash(' '.join(message_parts), 'warning')
        
    except Exception as e:
        current_app.logger.error(f'Error sending settlement reports: {e}')
        flash('Error sending settlement reports. Please try again.', 'error')
    
    return redirect(url_for('main.view_group', share_token=share_token))


@main.route('/group/<share_token>/reopen', methods=['POST'])
def reopen_group(share_token):
    """Reopen a settled or expired group (admin only)."""
    # Find group regardless of is_active status to allow reopening expired groups
    group = Group.query.filter_by(share_token=share_token).first_or_404()
    
    # Check if user is admin
    is_admin = verify_admin_access(share_token, group)
    if not is_admin:
        abort(403)
    
    if not group.is_settled and not group.is_expired and group.is_active:
        flash('Group is already active and not settled or expired.', 'info')
        return redirect(url_for('main.view_group', share_token=share_token))
    
    try:
        # Reopen the group
        group.is_active = True  # Reactivate the group
        group.is_settled = False
        group.settled_at = None
        
        # If group was expired, remove the expiration date to make it a normal group
        if group.is_expired:
            group.expires_at = None
            flash('Expired group has been reopened and converted to a normal group (expiration date removed). You can now add more expenses.', 'success')
        else:
            flash('Group has been reopened successfully! You can now add more expenses.', 'success')
        
        # Create audit log entry for reopening
        from app.models import AuditLog
        audit_log = AuditLog(
            group_id=group.id,
            action='group_reopened',
            description=f'Group reopened by admin. Expiration date {"removed" if group.is_expired else "not applicable"}.',
            details={
                'was_expired': group.is_expired,
                'was_settled': group.is_settled,
                'expiration_removed': group.is_expired
            },
            performed_by='Admin'
        )
        db.session.add(audit_log)
        
        db.session.commit()
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Error reopening group: {e}')
        flash('Error reopening group. Please try again.', 'error')
    
    return redirect(url_for('main.view_group', share_token=share_token))


@main.route('/group/<share_token>/remove-expiration', methods=['POST'])
def remove_expiration_date(share_token):
    """Remove the expiration date from a group (admin only)."""
    group = Group.query.filter_by(share_token=share_token, is_active=True).first_or_404()
    
    # Check if user is admin
    is_admin = verify_admin_access(share_token, group)
    if not is_admin:
        abort(403)
    
    # Check if group has an expiration date
    if not group.expires_at:
        flash('This group does not have an expiration date.', 'info')
        return redirect(url_for('main.view_group', share_token=share_token))
    
    try:
        # Store the old expiration date for logging
        old_expiration = group.expires_at
        
        # Remove the expiration date
        group.expires_at = None
        
        # Create audit log entry
        from app.models import AuditLog
        audit_log = AuditLog(
            group_id=group.id,
            action='expiration_removed',
            description=f'Group expiration date removed by admin. Was set to expire on {old_expiration.strftime("%B %d, %Y")}.',
            details={
                'old_expiration_date': old_expiration.isoformat(),
                'action_type': 'expiration_removal'
            },
            performed_by='Admin'
        )
        db.session.add(audit_log)
        
        db.session.commit()
        flash('Expiration date has been removed. This group will no longer expire automatically.', 'success')
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Error removing expiration date: {e}')
        flash('Error removing expiration date. Please try again.', 'error')
    
    return redirect(url_for('main.view_group', share_token=share_token))


@main.route('/group/<share_token>/delete', methods=['POST'])
def delete_group(share_token):
    """Permanently delete a group and all associated data (admin only)."""
    group = Group.query.filter_by(share_token=share_token).first_or_404()
    
    # Check if user is admin
    is_admin = verify_admin_access(share_token, group)
    if not is_admin:
        abort(403)

    # Check if group is already deleted
    if not group.is_active:
        flash(f'Group "{group.name}" has already been deleted.', 'info')
        return redirect(url_for('main.index'))

    try:
        # Store group info for processing
        group_name = group.name
        group_id = group.id
        is_settled = group.is_settled

        current_app.logger.info(f'Starting deletion process for group "{group_name}" (ID: {group_id})')
        
        # If group is not settled, send settlement email first
        if not is_settled:
            # Get balances before deletion
            balances = group.get_balances(group.currency)
            settlements = calculate_settlements(balances)
            
            # Check if there are any non-zero balances to report
            has_balances = any(abs(balance) > 0.01 for balance in balances.values())
            
            if has_balances:
                from app.utils import send_final_settlement_report
                
                # Send deletion settlement reports to participants
                success_count = 0
                failed_reasons = []
                no_email_count = 0
                
                for participant in group.participants:
                    if participant.email:
                        success, message = send_final_settlement_report(
                            participant.email,
                            participant.name,
                            group.name,
                            balances,
                            settlements,
                            group.participants,
                            group.currency,
                            is_period_settlement=False,
                            is_deletion_settlement=True,  # Special flag for deletion
                            group_id=group.id,
                            participant_id=participant.id,
                            share_token=group.share_token
                        )
                        if success:
                            success_count += 1
                        else:
                            failed_reasons.append(f"{participant.name}: {message}")
                    else:
                        no_email_count += 1
                
                # Log and provide feedback about email outcomes
                if success_count > 0:
                    current_app.logger.info(f'Sent deletion settlement reports to {success_count} participants for group: {group_name}')
                
                # Create detailed feedback about email sending
                total_with_email = sum(1 for p in group.participants if p.email)
                if total_with_email > 0:
                    if success_count == total_with_email:
                        flash(f'Final settlement reports sent to all {success_count} participants with email addresses.', 'success')
                    elif success_count > 0:
                        flash(f'Final settlement reports sent to {success_count} out of {total_with_email} participants with email addresses.', 'warning')
                        if failed_reasons:
                            # Group failures by type for clearer messaging
                            rate_limited = [r for r in failed_reasons if 'rate limit' in r.lower()]
                            delivery_failed = [r for r in failed_reasons if 'rate limit' not in r.lower()]
                            
                            if rate_limited:
                                flash(f'Some participants hit email rate limits: {"; ".join(rate_limited)}', 'warning')
                            if delivery_failed:
                                flash(f'Email delivery failed for some participants: {"; ".join(delivery_failed)}', 'warning')
                    else:
                        flash(f'Failed to send settlement reports to any participants. Details: {"; ".join(failed_reasons)}', 'error')
                
                if no_email_count > 0:
                    flash(f'{no_email_count} participants have no email addresses and will not receive settlement reports.', 'info')
        
        # Use the group's delete method to remove all associated data
        current_app.logger.info(f'Calling delete_group method for "{group_name}"')
        deletion_summary = group.delete_group()
        current_app.logger.info(f'Delete method completed. Summary: {deletion_summary}')

        # Verify deletion
        verification_group = Group.query.filter_by(share_token=share_token).first()
        if verification_group:
            current_app.logger.error(f'CRITICAL: Group "{group_name}" still exists after delete_group() method!')
            raise Exception(f'Group deletion failed - group still exists in database')
        else:
            current_app.logger.info(f'Verified: Group "{group_name}" successfully removed from database')

        # Clear admin session for this group
        session.pop(f'admin_{share_token}', None)
        session.pop(f'admin_participant_{share_token}', None)
        session.pop(f'participant_{share_token}', None)
        
        # Log the deletion details
        current_app.logger.warning(f'Group "{group_name}" permanently deleted by admin from IP {request.remote_addr}: {deletion_summary}')
        
        flash(f'Group "{group_name}" has been permanently deleted along with all data '
              f'({deletion_summary["expenses"]} expenses, {deletion_summary["participants"]} participants, '
              f'{deletion_summary["audit_logs"]} audit logs).', 'success')
        
        # Redirect to home page since the group no longer exists
        return redirect(url_for('main.index'))
        
    except Exception as e:
        # Rollback is handled by delete_group method, but just in case
        db.session.rollback()
        current_app.logger.error(f'Error deleting group "{group.name}": {str(e)}', exc_info=True)
        flash(f'Error deleting group: {str(e)}. Please try again or contact support.', 'error')

        # Try to return to admin panel if group still exists
        try:
            return redirect(url_for('main.admin_panel', admin_token=group.admin_token))
        except:
            return redirect(url_for('main.index'))


@main.route('/admin/<admin_token>')
def admin_panel(admin_token):
    """Admin panel for group management."""
    # Admin should be able to access inactive groups to reopen them
    group = Group.query.filter_by(admin_token=admin_token).first_or_404()
    
    # Log successful admin access
    current_app.logger.info(f"Admin panel accessed for group '{group.name}' from IP {request.remote_addr}")
    
    # Set secure admin session - this grants full access
    set_secure_admin_session(group.share_token, admin_token)
    
    # Admin link grants immediate access without needing to join
    # Create a temporary admin participant session for group access
    session[f'admin_participant_{group.share_token}'] = True
    current_app.logger.info(f"Admin granted direct group access without participant session")
    
    return render_template('admin_panel.html', group=group, admin_token=admin_token)


@main.route('/admin/<admin_token>/add-participant', methods=['POST'])
def admin_add_participant(admin_token: str) -> Any:
    """Add participant directly via admin panel."""
    group = Group.query.filter_by(admin_token=admin_token, is_active=True).first_or_404()
    
    # Verify admin access
    is_admin = verify_admin_access(group.share_token, group)
    if not is_admin:
        abort(403)
    
    # Check if group allows new participants
    if group.is_expired or group.is_settled:
        flash('Cannot add participants to expired or settled groups.', 'error')
        return redirect(url_for('main.admin_panel', admin_token=admin_token))
    
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip()
    
    if not name:
        flash('Participant name is required.', 'error')
        return redirect(url_for('main.admin_panel', admin_token=admin_token))
    
    if len(name) > 50:
        flash('Participant name must be 50 characters or less.', 'error')
        return redirect(url_for('main.admin_panel', admin_token=admin_token))
    
    # Validate email if provided
    if email:
        import re
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email):
            flash('Please enter a valid email address.', 'error')
            return redirect(url_for('main.admin_panel', admin_token=admin_token))
    
    try:
        # Check if participant with same name already exists
        existing_participant = Participant.query.filter_by(group_id=group.id, name=name).first()
        if existing_participant:
            flash(f'A participant named "{name}" already exists in this group.', 'error')
            return redirect(url_for('main.admin_panel', admin_token=admin_token))
        
        # Create participant
        participant = Participant(
            name=name,
            email=email if email else None,
            group_id=group.id,
            color=get_participant_color(len(group.participants))
        )
        
        db.session.add(participant)
        db.session.flush()  # Get participant ID
        
        # Add to known emails if email provided
        if email:
            known_email = KnownEmail.query.filter_by(email=email).first()
            if not known_email:
                known_email = KnownEmail(email=email)
                db.session.add(known_email)
        
        # Create audit log entry
        from app.utils import log_audit_action
        log_audit_action(
            group_id=group.id,
            action='participant_added',
            description=f'Admin added participant "{name}"' + (f' with email {email}' if email else ''),
            performed_by='Admin',
            participant_id=participant.id,
            details={
                'participant_name': name,
                'participant_email': email,
                'added_by_admin': True
            }
        )
        
        db.session.commit()
        
        # Broadcast real-time update to all group members
        from app.socketio_events.group_events import broadcast_participant_joined
        broadcast_participant_joined(group.share_token, {
            'id': participant.id,
            'name': participant.name,
            'email': participant.email,
            'color': participant.color
        })
        
        # Send personalized invitation email if email was provided
        email_sent = False
        if email:
            from app.utils import send_precreated_participant_invitation
            email_sent = send_precreated_participant_invitation(
                to_email=email,
                participant_name=name,
                group_name=group.name,
                participant=participant,
                group_id=group.id
            )
        
        if email and email_sent:
            flash(f'Participant "{name}" has been added and invitation sent to {email}!', 'success')
        elif email and not email_sent:
            flash(f'Participant "{name}" has been added, but invitation email failed to send. You can share their personal link manually.', 'warning')
        else:
            flash(f'Participant "{name}" has been added successfully!', 'success')
        
    except IntegrityError:
        db.session.rollback()
        flash('Error adding participant. Please try again.', 'error')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Error adding participant via admin: {e}')
        flash('An unexpected error occurred. Please try again.', 'error')
    
    return redirect(url_for('main.admin_panel', admin_token=admin_token))


@main.route('/admin/<admin_token>/resend-invitation', methods=['POST'])
def admin_resend_invitation(admin_token: str) -> Any:
    """Resend invitation email for a participant."""
    group = Group.query.filter_by(admin_token=admin_token).first_or_404()
    
    # Verify admin access
    is_admin = verify_admin_access(group.share_token, group)
    if not is_admin:
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    
    try:
        data = request.get_json()
        participant_id = data.get('participant_id')
        email = data.get('email')
        name = data.get('name')
        
        if not all([participant_id, email, name]):
            return jsonify({'success': False, 'message': 'Missing required fields'}), 400
        
        # Find the participant
        participant = Participant.query.filter_by(id=participant_id, group_id=group.id).first()
        if not participant:
            return jsonify({'success': False, 'message': 'Participant not found'}), 404
        
        # Send the invitation
        from app.utils import send_precreated_participant_invitation
        success = send_precreated_participant_invitation(
            to_email=email,
            participant_name=name,
            group_name=group.name,
            participant=participant,
            group_id=group.id
        )
        
        if success:
            current_app.logger.info(f'Admin resent invitation to {email} for participant {name} in group {group.name}')
            
            # Log audit entry for invitation resend
            from app.utils import log_audit_action
            log_audit_action(
                group_id=group.id,
                action='invitation_resent',
                description=f'Admin resent invitation to {name}',
                performed_by='Admin',
                participant_id=participant_id,
                details={
                    'participant_name': name,
                    'participant_email': email,
                    'resent_by_admin': True
                }
            )
            
            return jsonify({'success': True, 'message': 'Invitation sent successfully'})
        else:
            return jsonify({'success': False, 'message': 'Failed to send email'}), 500
            
    except Exception as e:
        current_app.logger.error(f'Error resending invitation: {e}')
        return jsonify({'success': False, 'message': 'Server error'}), 500


@main.route('/group/<share_token>/invite', methods=['GET', 'POST'])
def invite_member(share_token):
    """Invite member via email."""
    group = Group.query.filter_by(share_token=share_token, is_active=True).first_or_404()
    
    # Check if user is admin or participant
    is_admin = verify_admin_access(share_token, group)
    participant, _ = verify_participant_access(share_token)
    
    if not is_admin and not participant:
        return redirect(url_for('main.join_group_direct', share_token=share_token))
    
    # Use admin as inviter if no participant
    inviter_name = participant.name if participant else "Group Admin"
    
    form = ShareGroupForm()
    
    # Handle simple email form from group-created page (no 'name' field, only email)
    if request.method == 'POST' and 'email' in request.form and 'name' not in request.form and 'message' not in request.form:
        email = request.form.get('email', '').strip()
        if email:
            success = send_group_invitation(
                to_email=email,
                group_name=group.name,
                share_token=share_token,
                inviter_name=inviter_name,
                personal_message='',
                group_id=group.id,
                is_settled=group.is_settled
            )
            if success:
                flash(f'Invitation sent to {email}!', 'success')
            else:
                flash(f'Email delivery failed, but you can share manually', 'warning')
                base_url = current_app.config['BASE_URL']
                join_url = f'{base_url}/join/{share_token}'
                flash(f'Share this link: {join_url}', 'info')
        return redirect(url_for('main.group_created', share_token=share_token))
    
    # Handle participant addition form from group page (has 'name' field)
    if request.method == 'POST' and 'name' in request.form:
        participant_name = request.form.get('name', '').strip()
        participant_email = request.form.get('email', '').strip()
        
        if not participant_name:
            flash('Participant name is required.', 'error')
            return redirect(url_for('main.view_group', share_token=share_token))
        
        # Check if name is already taken in this group
        existing_participant = Participant.query.filter(
            Participant.group_id == group.id,
            db.func.lower(Participant.name) == participant_name.lower()
        ).first()
        
        if existing_participant:
            flash(f'A participant named "{participant_name}" already exists in this group.', 'error')
            return redirect(url_for('main.view_group', share_token=share_token))
        
        try:
            # Create new participant
            new_participant = Participant(
                name=participant_name,
                email=participant_email if participant_email else None,
                group_id=group.id,
                color=get_participant_color(len(group.participants))
            )

            db.session.add(new_participant)
            db.session.flush()  # Get participant ID

            # Add to known emails if email provided
            if participant_email:
                from app.utils import update_known_email
                update_known_email(participant_email, participant_name)

            # Create audit log entry
            from app.utils import log_audit_action
            # Only pass participant_id if it's a real integer (not 'admin' or 'viewer' virtual participants)
            performed_by_id = participant.id if participant and isinstance(participant.id, int) else None

            log_audit_action(
                group_id=group.id,
                action='participant_added',
                description=f'Added participant: {participant_name}',
                performed_by=inviter_name,
                performed_by_participant_id=performed_by_id,
                participant_id=new_participant.id if new_participant else None,
                details={
                    'participant_name': participant_name,
                    'participant_email': participant_email,
                    'added_by_admin': is_admin
                }
            )
            
            db.session.commit()
            
            # Broadcast real-time update to all group members
            from app.socketio_events.group_events import broadcast_participant_joined
            broadcast_participant_joined(group.share_token, {
                'id': new_participant.id,
                'name': new_participant.name,
                'email': new_participant.email,
                'color': new_participant.color
            })
            
            # Send invitation email if email was provided
            if participant_email:
                from app.utils import send_precreated_participant_invitation
                success = send_precreated_participant_invitation(
                    to_email=participant_email,
                    participant_name=participant_name,
                    group_name=group.name,
                    share_token=share_token,
                    inviter_name=inviter_name,
                    personal_message='',
                    access_token=new_participant.access_token,
                    group_id=group.id
                )
                
                if success:
                    flash(f'Added "{participant_name}" and sent invitation to {participant_email}!', 'success')
                else:
                    flash(f'Added "{participant_name}" but email delivery failed. You can share their personal link manually.', 'warning')
            else:
                flash(f'Added "{participant_name}" to the group successfully!', 'success')
                
        except Exception as e:
            db.session.rollback()
            import traceback
            current_app.logger.error(f'Error adding participant: {e}')
            current_app.logger.error(f'Traceback: {traceback.format_exc()}')
            flash('Failed to add participant. Please try again.', 'error')
        
        return redirect(url_for('main.view_group', share_token=share_token))
    
    if form.validate_on_submit():
        email = form.email.data.strip() if form.email.data else ''
        
        # Check if this email already belongs to a participant in this group
        existing_participant = Participant.query.filter_by(email=email, group_id=group.id).first()
        
        if existing_participant:
            # Send invitation to existing participant with their personal link
            success = send_group_invitation(
                to_email=email,
                group_name=group.name,
                share_token=share_token,
                inviter_name=inviter_name,
                personal_message=form.message.data.strip() if form.message.data else '',
                group_id=group.id,
                participant_id=existing_participant.id,
                is_settled=group.is_settled
            )
        else:
            # Create a new participant for this invitation (pre-created participant pattern)
            try:
                # Generate a name from email (user@example.com -> User)
                email_name = email.split('@')[0].replace('.', ' ').replace('_', ' ').title()

                # Create participant with email-derived name
                new_participant = Participant(
                    name=email_name,
                    email=email,
                    group_id=group.id,
                    color=get_participant_color(len(group.participants))
                )
                
                db.session.add(new_participant)
                db.session.flush()  # Get participant ID
                
                # Add to known emails
                from app.utils import update_known_email
                update_known_email(email, new_participant.name)
                
                # Create audit log entry
                from app.utils import log_audit_action
                log_audit_action(
                    group_id=group.id,
                    action='participant_invited',
                    description=f'Participant invited via email: {email}',
                    performed_by=inviter_name,
                    participant_id=new_participant.id,
                    details={
                        'participant_email': email,
                        'invited_by': inviter_name,
                        'pre_created': True
                    }
                )
                
                db.session.commit()
                
                # Broadcast real-time update to all group members
                from app.socketio_events.group_events import broadcast_participant_joined
                broadcast_participant_joined(group.share_token, {
                    'id': new_participant.id,
                    'name': new_participant.name,
                    'email': new_participant.email,
                    'color': new_participant.color
                })
                
                # Send personalized invitation email with direct access link
                from app.utils import send_precreated_participant_invitation
                success = send_precreated_participant_invitation(
                    to_email=email,
                    participant_name=new_participant.name,
                    group_name=group.name,
                    share_token=share_token,
                    inviter_name=inviter_name,
                    personal_message=form.message.data.strip() if form.message.data else '',
                    access_token=new_participant.access_token,
                    group_id=group.id
                )
                
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f'Error creating pre-invited participant: {e}')
                # Fallback to regular invitation
                success = send_group_invitation(
                    to_email=email,
                    group_name=group.name,
                    share_token=share_token,
                    inviter_name=inviter_name,
                    personal_message=form.message.data.strip() if form.message.data else '',
                    group_id=group.id,
                    is_settled=group.is_settled
                )
        
        if success:
            flash(f'Personal invitation sent to {email}!', 'success')
        else:
            flash(f'Share this link: {join_url}', 'info') 
            flash(f'Or share the group code: {share_token}', 'info')
        
        return redirect(url_for('main.view_group', share_token=share_token))
    
    return render_template('invite_member.html', form=form, group=group, participant=participant, is_admin=is_admin)


@main.route('/find-groups', methods=['GET', 'POST'])
def find_groups():
    """Find active groups by email address."""
    # Handle import from email link
    import_email = request.args.get('import_email')
    if import_email:
        # Find all active groups where this email participates OR is the creator
        participant_groups = db.session.query(Group).join(Participant).filter(
            Participant.email == import_email.strip().lower(),
            Group.is_active.is_(True)
        )
        creator_groups = db.session.query(Group).filter(
            Group.creator_email == import_email.strip().lower(),
            Group.is_active.is_(True)
        )
        active_groups = participant_groups.union(creator_groups).order_by(Group.created_at.desc()).all()
        
        # Make session permanent BEFORE storing any tokens
        session.permanent = True
        current_app.logger.info(f"Set permanent session for email import, lifetime: {current_app.config.get('PERMANENT_SESSION_LIFETIME')}")
        
        # Import all groups to current session (if any exist)
        imported_count = 0
        for group in active_groups:
            # Grant appropriate access to all found groups
            is_creator = group.creator_email and group.creator_email.lower() == import_email.strip().lower()
            if is_creator:
                # Grant admin access if user is the creator
                from app.utils import set_secure_admin_session
                set_secure_admin_session(group.share_token, group.admin_token)
                current_app.logger.info(f"Imported group '{group.name}' with ADMIN access for creator via email link")
            else:
                # Grant viewer access for participant
                session[f'viewer_{group.share_token}'] = True
                current_app.logger.info(f"Imported group '{group.name}' with viewer access for participant via email link")
            imported_count += 1
        
        if imported_count > 0:
            flash(f'Successfully imported {imported_count} group(s) to this device!', 'success')
        else:
            # Be honest about no groups found, but don't reveal this during normal search
            flash('No active groups found for this email address.', 'info')
        
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        if not email:
            flash('Please enter an email address.', 'error')
            return render_template('find_groups.html')
        
        # Find all active groups where this email participates OR is the creator
        participant_groups = db.session.query(Group).join(Participant).filter(
            Participant.email == email,
            Group.is_active.is_(True)
        )
        creator_groups = db.session.query(Group).filter(
            Group.creator_email == email,
            Group.is_active.is_(True)
        )
        active_groups = participant_groups.union(creator_groups).order_by(Group.created_at.desc()).all()
        
        # Check if user wants to import all groups to current device
        if request.form.get('action') == 'import' and active_groups:
            # Make session permanent BEFORE storing tokens
            session.permanent = True
            current_app.logger.info(f"Set permanent session for find groups import, lifetime: {current_app.config.get('PERMANENT_SESSION_LIFETIME')}")
            
            # Import all groups to current session
            imported_count = 0
            for group in active_groups:
                # Grant appropriate access to all found groups
                is_creator = group.creator_email and group.creator_email.lower() == email.lower()
                if is_creator:
                    # Grant admin access if user is the creator
                    from app.utils import set_secure_admin_session
                    set_secure_admin_session(group.share_token, group.admin_token)
                    current_app.logger.info(f"Imported group '{group.name}' with ADMIN access for creator via find groups")
                else:
                    # Grant viewer access for participant
                    session[f'viewer_{group.share_token}'] = True
                    current_app.logger.info(f"Imported group '{group.name}' with viewer access for participant via find groups")
                imported_count += 1
            
            # Make session permanent for 90-day persistence
            session.permanent = True
            flash(f'Successfully imported {imported_count} group(s) to this device!', 'success')
            return redirect(url_for('main.index'))
        else:
            # Always send email or show generic success message for security
            # Don't reveal whether groups exist or not
            if active_groups:
                from app.utils import send_group_links_email
                success = send_group_links_email(email, active_groups)
                # Always show generic success even if email fails
            
            # Generic response regardless of whether groups were found or email succeeded
            return render_template('find_groups.html', 
                                  email_sent=True,
                                  found_email=email)
        
        return render_template('find_groups.html', 
                              found_groups=session.get('found_groups'),
                              found_email=session.get('found_email'))
    
    return render_template('find_groups.html')


@main.route('/api/known-emails')
def get_known_emails():
    """API endpoint for email autocomplete."""
    query = request.args.get('q', '').strip()
    if len(query) < 2:
        return jsonify([])
    
    emails = KnownEmail.query.filter(
        KnownEmail.email.ilike(f'%{query}%')
    ).order_by(
        KnownEmail.usage_count.desc(),
        KnownEmail.last_used.desc()
    ).limit(10).all()
    
    return jsonify([{
        'email': email.email,
        'name': email.name
    } for email in emails])


@main.errorhandler(404)
def not_found_error(error):
    """Handle 404 errors."""
    return render_template('404.html'), 404


@main.route('/group/<share_token>/delete-expense/<int:expense_id>', methods=['POST'])
def delete_expense(share_token, expense_id):
    """Delete an expense from the group."""
    participant, group = verify_participant_access(share_token)
    if not participant:
        return render_template('404.html'), 404
    
    # Allow all participants to delete expenses (not just admins)
    
    if group.is_settled:
        flash('Cannot delete expenses from a settled group.', 'error')
        return redirect(url_for('main.view_group', share_token=share_token))
    
    # Find the expense
    expense = Expense.query.filter_by(id=expense_id, group_id=group.id).first()
    if not expense:
        flash('Expense not found.', 'error')
        return redirect(url_for('main.view_group', share_token=share_token))
    
    try:
        # Store expense data for broadcasting before deletion
        expense_data = {
            'id': expense.id,
            'title': expense.title,
            'amount': float(expense.amount),
            'currency': expense.currency
        }

        # Log the expense deletion before deletion
        from app.utils import log_audit_action
        log_audit_action(
            group_id=group.id,
            action='expense_deleted',
            description=f'Deleted expense "{expense.title}" ({expense.currency}{expense.original_amount})',
            performed_by=participant.name,
            performed_by_participant_id=participant.id if isinstance(participant.id, int) else None,
            expense_id=expense.id,
            details={
                'expense_title': expense.title,
                'expense_amount': float(expense.amount),
                'expense_currency': expense.currency,
                'expense_category': expense.category,
                'paid_by_name': expense.paid_by.name,
                'split_count': len(expense.expense_shares)
            }
        )
        
        # Delete expense shares first (due to foreign key constraints)
        ExpenseShare.query.filter_by(expense_id=expense_id).delete()
        
        # Delete the expense
        db.session.delete(expense)
        db.session.commit()
        
        # Broadcast real-time update to all group members
        from app.socketio_events.group_events import broadcast_expense_deleted, broadcast_balance_updated
        broadcast_expense_deleted(group.share_token, expense_data)
        
        # Also broadcast updated balances after deletion
        balances = group.get_balances()
        broadcast_balance_updated(group.share_token, {
            'balances': {str(p_id): {'amount': float(balance), 'currency': group.currency} 
                       for p_id, balance in balances.items()}
        })
        
        flash(f'Expense "{expense.title}" has been deleted.', 'success')
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Error deleting expense {expense_id}: {e}')
        flash('Failed to delete expense. Please try again.', 'error')
    
    return redirect(url_for('main.view_group', share_token=share_token))


@main.route('/group/<share_token>/remove-participant/<int:participant_id>', methods=['POST'])
def remove_participant(share_token, participant_id):
    """Remove a participant from the group."""
    current_participant, group = verify_participant_access(share_token)
    if not current_participant:
        return render_template('404.html'), 404
    
    # Check if user is admin
    is_admin = verify_admin_access(share_token, group)
    if not is_admin:
        current_app.logger.warning(f"Unauthorized participant removal attempt by {current_participant.name} for participant {participant_id} in group {group.name} from IP {request.remote_addr}")
        flash('Only group admins can remove participants.', 'error')
        return redirect(url_for('main.view_group', share_token=share_token))
    
    if group.is_settled:
        flash('Cannot remove participants from a settled group.', 'error')
        return redirect(url_for('main.view_group', share_token=share_token))
    
    # Find the participant to remove
    participant_to_remove = Participant.query.filter_by(id=participant_id, group_id=group.id).first()
    if not participant_to_remove:
        flash('Participant not found.', 'error')
        return redirect(url_for('main.view_group', share_token=share_token))
    
    # Check if this is the last participant
    if len(group.participants) <= 1:
        flash('Cannot remove the last participant from the group.', 'error')
        return redirect(url_for('main.view_group', share_token=share_token))
    
    # Check if participant has any expenses
    participant_expenses = Expense.query.filter_by(paid_by_id=participant_id, group_id=group.id).all()
    participant_shares = ExpenseShare.query.filter_by(participant_id=participant_id).join(Expense).filter(Expense.group_id == group.id).all()
    
    if participant_expenses or participant_shares:
        # Get current balance for this participant
        balances = group.get_balances()
        participant_balance = float(balances.get(participant_id, 0.0))
        
        if abs(participant_balance) > 0.01:  # Has outstanding balance
            flash(
                f'Cannot remove {participant_to_remove.name} - they have outstanding expenses and a balance of {format_currency(participant_balance, group.currency)}. '
                f'Please settle their expenses first or transfer their expenses to another participant.',
                'error'
            )
            return redirect(url_for('main.view_group', share_token=share_token))
    
    try:
        # Handle expense retention - reassign to group admin or first participant
        if participant_expenses:
            # Find a suitable participant to transfer expenses to (prefer admin, then first participant)
            transfer_to = None
            for p in group.participants:
                if p.id != participant_id and p.is_admin:
                    transfer_to = p
                    break
            if not transfer_to:
                for p in group.participants:
                    if p.id != participant_id:
                        transfer_to = p
                        break
            
            if transfer_to:
                for expense in participant_expenses:
                    expense.paid_by_id = transfer_to.id
                    
                # Log expense transfers
                from app.utils import log_audit_action
                performed_by_id = current_participant.id if isinstance(current_participant.id, int) else None
                log_audit_action(
                    group_id=group.id,
                    action='expenses_transferred',
                    description=f'Transferred {len(participant_expenses)} expenses from {participant_to_remove.name} to {transfer_to.name}',
                    performed_by=current_participant.name,
                    performed_by_participant_id=performed_by_id,
                    participant_id=participant_id,
                    details={
                        'from_participant': participant_to_remove.name,
                        'to_participant': transfer_to.name,
                        'expense_count': len(participant_expenses),
                        'expense_ids': [e.id for e in participant_expenses]
                    }
                )
        
        # Remove expense shares
        for share in participant_shares:
            db.session.delete(share)
        
        # Log the participant removal
        from app.utils import log_audit_action
        performed_by_id = current_participant.id if isinstance(current_participant.id, int) else None
        log_audit_action(
            group_id=group.id,
            action='participant_removed',
            description=f'Removed participant {participant_to_remove.name}',
            performed_by=current_participant.name,
            performed_by_participant_id=performed_by_id,
            participant_id=participant_id,
            details={
                'removed_participant_name': participant_to_remove.name,
                'removed_participant_email': participant_to_remove.email,
                'had_expenses': len(participant_expenses) > 0,
                'had_shares': len(participant_shares) > 0
            }
        )
        
        # Store participant data for broadcasting before deletion
        participant_data = {
            'id': participant_to_remove.id,
            'name': participant_to_remove.name,
            'email': participant_to_remove.email,
            'color': participant_to_remove.color
        }
        
        # Remove the participant
        db.session.delete(participant_to_remove)
        db.session.commit()
        
        # Broadcast real-time update to all group members
        from app.socketio_events.group_events import broadcast_participant_removed
        broadcast_participant_removed(group.share_token, participant_data)
        
        flash(f'{participant_to_remove.name} has been removed from the group.', 'success')
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Error removing participant {participant_id}: {e}')
        flash('Failed to remove participant. Please try again.', 'error')
    
    return redirect(url_for('main.view_group', share_token=share_token))


@main.route('/group/<share_token>/edit-participant/<int:participant_id>', methods=['POST'])
def edit_participant(share_token, participant_id):
    """Edit a participant's details."""
    current_participant, group = verify_participant_access(share_token)
    if not current_participant:
        return render_template('404.html'), 404
    
    # Check if user is admin
    is_admin = verify_admin_access(share_token, group)
    if not is_admin:
        current_app.logger.warning(f"Unauthorized participant edit attempt by {current_participant.name} for participant {participant_id} in group {group.name} from IP {request.remote_addr}")
        flash('Only group admins can edit participants.', 'error')
        return redirect(url_for('main.view_group', share_token=share_token))
    
    # Find the participant to edit
    participant_to_edit = Participant.query.filter_by(id=participant_id, group_id=group.id).first()
    if not participant_to_edit:
        flash('Participant not found.', 'error')
        return redirect(url_for('main.view_group', share_token=share_token))
    
    # Get form data
    new_name = request.form.get('name', '').strip()
    new_email = request.form.get('email', '').strip()
    
    if not new_name:
        flash('Participant name is required.', 'error')
        return redirect(url_for('main.view_group', share_token=share_token))
    
    # Check if name is already taken by another participant in this group
    existing_participant = Participant.query.filter(
        Participant.group_id == group.id,
        Participant.id != participant_id,
        db.func.lower(Participant.name) == new_name.lower()
    ).first()
    
    if existing_participant:
        flash(f'A participant named "{new_name}" already exists in this group.', 'error')
        return redirect(url_for('main.view_group', share_token=share_token))
    
    try:
        # Store old values for logging
        old_name = participant_to_edit.name
        old_email = participant_to_edit.email
        
        # Update participant details
        participant_to_edit.name = new_name
        participant_to_edit.email = new_email if new_email else None
        
        db.session.commit()
        
        # Log the participant update
        from app.utils import log_audit_action
        changes = []
        if old_name != new_name:
            changes.append(f'name: "{old_name}" → "{new_name}"')
        if old_email != new_email:
            old_email_display = old_email or 'no email'
            new_email_display = new_email or 'no email'
            changes.append(f'email: "{old_email_display}" → "{new_email_display}"')

        # Only pass participant_id if it's a real integer (not 'admin' or 'viewer' virtual participants)
        performed_by_id = current_participant.id if isinstance(current_participant.id, int) else None

        log_audit_action(
            group_id=group.id,
            action='participant_updated',
            description=f'Updated participant {new_name}',
            performed_by=current_participant.name,
            performed_by_participant_id=performed_by_id,
            participant_id=participant_id,
            details={
                'old_name': old_name,
                'new_name': new_name,
                'old_email': old_email,
                'new_email': new_email,
                'changes': changes
            }
        )
        
        # Broadcast real-time update to all group members
        from app.socketio_events.group_events import broadcast_participant_updated
        participant_data = {
            'id': participant_to_edit.id,
            'name': participant_to_edit.name,
            'email': participant_to_edit.email,
            'color': participant_to_edit.color,
            'old_name': old_name
        }
        broadcast_participant_updated(group.share_token, participant_data)
        
        flash(f'Participant "{new_name}" has been updated successfully.', 'success')
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Error editing participant {participant_id}: {e}')
        flash('Failed to update participant. Please try again.', 'error')
    
    return redirect(url_for('main.view_group', share_token=share_token))


@main.route('/group/<share_token>/history')
def group_history(share_token):
    """View group history and audit log."""
    participant, group = verify_participant_access(share_token)
    if not participant:
        return render_template('404.html'), 404
    
    # Check if user is admin
    is_admin = verify_admin_access(share_token, group)
    
    # Get audit logs for this group
    from app.models import AuditLog
    limit = current_app.config.get('ACTIVITY_LOG_LIMIT', 100)
    audit_logs = AuditLog.query.filter_by(group_id=group.id).order_by(AuditLog.created_at.desc()).limit(limit).all()
    
    return render_template('group_history.html', 
                         group=group, 
                         participant=participant, 
                         is_admin=is_admin,
                         audit_logs=audit_logs)


@main.route('/group/<share_token>/download-history')
def download_history(share_token):
    """Download group history as a text file."""
    participant, group = verify_participant_access(share_token)
    if not participant:
        abort(404)
    
    # Generate the history content
    content = generate_history_text(group)
    
    # Create filename with group name and current date
    filename = f"{group.name.replace(' ', '_')}_history_{dt.now().strftime('%Y%m%d')}.txt"
    
    # Return as downloadable file
    return Response(
        content,
        mimetype='text/plain',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )


# Real-time updates removed - SSE implementation was problematic with Flask application context
# Users can manually refresh to see updates, which is appropriate for expense splitting use case


@main.errorhandler(403)
def forbidden_error(error):
    """Handle 403 errors."""
    return render_template('403.html'), 403


@main.errorhandler(410)
def gone_error(error):
    """Handle 410 errors."""
    return render_template('410.html'), 410


@main.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    db.session.rollback()
    return render_template('500.html'), 500
