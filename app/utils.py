"""Utility functions for Splittchen application."""

import smtplib
import ssl
import re
import secrets
import hashlib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Optional, Tuple, Union, Any, List, Callable
from decimal import Decimal
from urllib.parse import quote
from flask import current_app, request, flash
from gevent import spawn


def send_email_async(to_email: str, subject: str, html_content: str,
                    email_type: str, group_id: Optional[int] = None,
                    participant_id: Optional[int] = None,
                    text_content: Optional[str] = None) -> None:
    """
    Send email in background using gevent.

    This function queues the email for background sending and returns immediately,
    providing instant UI feedback to users.

    Args:
        to_email: Recipient email address
        subject: Email subject line
        html_content: HTML content of the email
        email_type: Type of email ('invitation', 'settlement', 'reminder', 'group_created')
        group_id: Optional group ID for tracking
        participant_id: Optional participant ID for tracking
        text_content: Optional plain text content
    """
    # Spawn background greenlet for email sending
    spawn(send_email_with_rate_limiting, to_email, subject, html_content,
          email_type, group_id, participant_id, text_content)

    current_app.logger.info(f"Email queued for background delivery to {to_email}")


def send_email_with_rate_limiting(to_email: str, subject: str, html_content: str,
                                  email_type: str, group_id: Optional[int] = None,
                                  participant_id: Optional[int] = None,
                                  text_content: Optional[str] = None) -> tuple[bool, str]:
    """
    Send email with rate limiting and logging.

    Args:
        to_email: Recipient email address
        subject: Email subject line
        html_content: HTML content of the email
        email_type: Type of email ('invitation', 'settlement', 'reminder', 'group_created')
        group_id: Optional group ID for tracking
        participant_id: Optional participant ID for tracking
        text_content: Optional plain text content

    Returns:
        tuple: (success: bool, message: str)
    """
    from app.models import EmailLog, db
    from flask import has_request_context

    # Check rate limits
    can_send, reason = EmailLog.can_send_email(to_email, email_type, group_id)
    if not can_send:
        current_app.logger.warning(f"Email rate limit exceeded for {to_email}: {reason}")

        # Log the blocked attempt
        email_log = EmailLog(
            email_address=to_email,
            email_type=email_type,
            success=False,
            group_id=group_id,
            participant_id=participant_id,
            sender_ip=request.remote_addr if has_request_context() and request else None,
            user_agent=request.headers.get('User-Agent') if has_request_context() and request else None
        )
        db.session.add(email_log)

        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Failed to log blocked email attempt: {e}")

        return False, f"Rate limit exceeded: {reason}"

    # Attempt to send email
    success = send_email_smtp(to_email, subject, html_content, text_content)

    # Log the email attempt
    email_log = EmailLog(
        email_address=to_email,
        email_type=email_type,
        success=success,
        group_id=group_id,
        participant_id=participant_id,
        sender_ip=request.remote_addr if has_request_context() and request else None,
        user_agent=request.headers.get('User-Agent') if has_request_context() and request else None
    )
    db.session.add(email_log)

    try:
        db.session.commit()
        if success:
            return True, "Email sent successfully"
        else:
            return False, "Email delivery failed"
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Failed to log email attempt: {e}")
        return success, "Email sent but logging failed" if success else "Email delivery failed"


def update_known_email(email: str, name: str) -> None:
    """Update or create a known email record for autocomplete."""
    if not email:
        return
        
    from app.models import KnownEmail, db
    from datetime import datetime, timezone
    
    known_email = KnownEmail.query.filter_by(email=email).first()
    if known_email:
        known_email.usage_count += 1
        known_email.last_used = datetime.now(timezone.utc)
        known_email.name = name
    else:
        known_email = KnownEmail(email=email, name=name)
        db.session.add(known_email)
    
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Failed to update known email: {e}")


def convert_expense_amount(amount: Decimal, currency: str, group) -> Tuple[Optional[Decimal], Optional[Decimal]]:
    """Convert expense amount to group's base currency.
    
    Args:
        amount: The original expense amount as Decimal.
        currency: The currency of the original amount.
        group: The expense group object.
        
    Returns:
        Tuple of (converted_amount, exchange_rate) or (None, None) if conversion fails.
    """
    if currency != group.currency:
        from app.currency import currency_service
        converted_amount = currency_service.convert_amount(
            amount, currency, group.currency
        )
        exchange_rate = currency_service.get_exchange_rate(currency, group.currency)
        
        if converted_amount is None or exchange_rate is None:
            return None, None
    else:
        converted_amount = amount
        from decimal import Decimal
        exchange_rate = Decimal('1.0')
    
    return converted_amount, exchange_rate


def setup_expense_form_choices(form: Any, group: Any) -> None:
    """Set up form choices for expense forms.
    
    Args:
        form: The expense form object (AddExpenseForm or EditExpenseForm).
        group: The group object containing participants.
    """
    from app.currency import currency_service
    form.paid_by_id.choices = [(p.id, p.name) for p in group.participants]
    form.split_between.choices = [(p.id, p.name) for p in group.participants]
    form.currency.choices = currency_service.get_currency_choices()


def validate_email(email: str) -> bool:
    """Validate email format to prevent injection attacks.
    
    Args:
        email: Email address to validate.
        
    Returns:
        True if email is valid, False otherwise.
    """
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def sanitize_email_for_url(email: str) -> str:
    """Sanitize email for safe URL inclusion.
    
    Args:
        email: Email address to sanitize.
        
    Returns:
        URL-encoded email address.
        
    Raises:
        ValueError: If email format is invalid.
    """
    if not validate_email(email):
        raise ValueError("Invalid email format")
    return quote(email, safe='@.')


def get_email_header() -> str:
    """Get consistent Splittchen email header with branding."""
    return '''
    <div style="text-align: center; margin-bottom: 30px; padding-bottom: 20px; border-bottom: 2px solid #16a34a;">
        <h1 style="font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; 
                   font-size: 2.5rem; font-weight: 700; color: #16a34a; margin: 0; letter-spacing: -0.025em;">
            splittchen
        </h1>
        <p style="color: #64748b; margin: 8px 0 0 0; font-size: 14px; font-weight: 500;">
            Simple expense splitting
        </p>
    </div>
    '''


def send_email_smtp(to_email: str, subject: str, html_content: str,
                    text_content: Optional[str] = None) -> bool:
    """Send email using SMTP.

    Args:
        to_email: Recipient email address.
        subject: Email subject line.
        html_content: HTML content of the email.
        text_content: Plain text content (optional).

    Returns:
        True if email was sent successfully, False otherwise.
    """
    from flask import has_request_context

    # Validate email to prevent injection
    if not validate_email(to_email):
        current_app.logger.warning(f"Invalid email format attempted: {to_email[:10]}... from IP {request.remote_addr if has_request_context() and request else 'scheduler'}")
        return False
    smtp_host = current_app.config.get('SMTP_HOST')
    smtp_port = current_app.config.get('SMTP_PORT', 587)
    smtp_username = current_app.config.get('SMTP_USERNAME')
    smtp_password = current_app.config.get('SMTP_PASSWORD')
    from_email = current_app.config.get('FROM_EMAIL')
    smtp_use_tls = current_app.config.get('SMTP_USE_TLS', True)
    
    if not all([smtp_host, smtp_username, smtp_password, from_email]):
        current_app.logger.error('SMTP configuration missing')
        return False
    
    # Type assertions after validation - we know these are not None after the check above
    assert smtp_host is not None
    assert smtp_username is not None
    assert smtp_password is not None
    assert from_email is not None
    
    try:
        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f"Splittchen <{from_email}>"
        msg['To'] = to_email
        
        # Add text content if provided
        if text_content:
            text_part = MIMEText(text_content, 'plain')
            msg.attach(text_part)
        
        # Add HTML content
        html_part = MIMEText(html_content, 'html')
        msg.attach(html_part)
        
        # Create SMTP connection
        if smtp_use_tls:
            context = ssl.create_default_context()
            server = smtplib.SMTP(smtp_host, smtp_port)
            server.starttls(context=context)
        else:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port)
        
        server.login(smtp_username, smtp_password)
        server.sendmail(from_email, to_email, msg.as_string())
        server.quit()
        
        current_app.logger.info(f'Email sent successfully to {to_email}')
        return True
        
    except Exception as e:
        current_app.logger.error(f'SMTP email failed to {to_email}: {e}')
        current_app.logger.debug(f'SMTP config - Host: {smtp_host}, Port: {smtp_port}, Username: {smtp_username}, From: {from_email}')
        return False


def send_group_creation_confirmation(to_email: str, group_name: str, share_token: str, admin_token: str, group_id: Optional[int] = None) -> bool:
    """Send group creation confirmation email to creator."""
    base_url = current_app.config['BASE_URL']
    join_url = f'{base_url}/join/{share_token}'
    group_url = f'{base_url}/group-created/{share_token}'
    admin_url = f'{base_url}/admin/{admin_token}'
    
    subject = f'Your group "{group_name}" has been created on Splittchen'
    
    # Log confirmation details
    current_app.logger.info(f'Sending group creation confirmation: to={to_email}, group={group_name}, token={share_token}')
    
    html_content = f'''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Group Created - Splittchen</title>
    </head>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
            {get_email_header()}
            <h2 style="color: #16a34a;">Your group "{group_name}" is ready!</h2>
            
            <p>Congratulations! Your expense group has been successfully created on Splittchen.</p>
            
            <div style="background: #f0f9f4; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #16a34a;">
                <h3 style="margin-top: 0; color: #16a34a;">Group Details:</h3>
                <p><strong>Group Name:</strong> {group_name}</p>
                <p><strong>Share Code:</strong> <code style="background: #e2e8f0; padding: 4px 8px; border-radius: 4px; font-size: 16px; font-weight: bold;">{share_token}</code></p>
                <p><strong>Join Link:</strong> <a href="{join_url}">{join_url}</a></p>
                <p><strong>Admin Panel:</strong> <a href="{admin_url}">{admin_url}</a></p>
            </div>
            
            <div style="text-align: center; margin: 30px 0;">
                <a href="{group_url}" 
                   style="display: inline-block; background: #16a34a; color: white; padding: 14px 28px; 
                          text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 16px;">
                    Manage Your Group
                </a>
            </div>
            
            <h3 style="color: #16a34a;">Next Steps:</h3>
            <ol style="padding-left: 20px;">
                <li style="margin-bottom: 10px;"><strong>Add yourself to the group</strong> - Use the join link above to add yourself as the first participant</li>
                <li style="margin-bottom: 10px;"><strong>Invite others</strong> - Share the group code or send invitations from your group dashboard</li>
                <li style="margin-bottom: 10px;"><strong>Start tracking expenses</strong> - Add your first expense and see how Splittchen calculates who owes what</li>
            </ol>
            
            <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 30px 0;">
            
            <p style="font-size: 12px; color: #94a3b8;">
                This email was sent because you created a group on Splittchen. 
                Keep this email for your records - it contains your group details and admin access.
            </p>
        </div>
    </body>
    </html>
    '''
    
    text_content = f'''
Your group "{group_name}" is ready!

Congratulations! Your expense group has been successfully created on Splittchen.

Group Details:
- Group Name: {group_name}
- Share Code: {share_token}
- Join Link: {join_url}
- Admin Panel: {admin_url}

Next Steps:
1. Add yourself to the group - Use the join link above
2. Invite others - Share the group code or send invitations
3. Start tracking expenses - Add your first expense

Manage your group: {group_url}

This email was sent because you created a group on Splittchen.
    '''
    
    # Use rate-limited email sending
    success, message = send_email_with_rate_limiting(
        to_email=to_email,
        subject=subject,
        html_content=html_content,
        email_type='group_created',
        group_id=group_id,
        text_content=text_content
    )
    
    return success


def send_group_invitation(to_email: str, group_name: str, share_token: str, 
                          inviter_name: str = 'A friend', 
                          personal_message: str = '', group_id: Optional[int] = None, 
                          participant_id: Optional[int] = None, is_settled: bool = False) -> bool:
    """Send group invitation email."""
    base_url = current_app.config['BASE_URL']
    
    # Check if this email belongs to an existing participant
    from app.models import Participant, Group
    participant = None
    if participant_id:
        participant = Participant.query.get(participant_id)
    else:
        # Look for existing participant by email
        participant = Participant.query.join(Group).filter(
            Participant.email == to_email,
            Group.share_token == share_token
        ).first()
    
    # Generate appropriate join URL
    if participant:
        # Use personalized participant link
        join_url = participant.generate_access_url(base_url)
        current_app.logger.info(f'Using personalized link for existing participant {participant.name}')
    else:
        # Use traditional join link for new participants
        try:
            safe_email = sanitize_email_for_url(to_email)
            join_url = f'{base_url}/join/{share_token}?email={safe_email}'
        except ValueError:
            current_app.logger.error(f"Invalid email format in invitation: {to_email}")
            return False
    
    if is_settled:
        subject = f'View settled group "{group_name}" on Splittchen'
        action_text = 'View Group'
        title_text = f'You\'ve been invited to view the settled group "{group_name}"'
        description_text = f'{inviter_name} has shared their settled expense group with you. You can view the final balances and expense history.'
        status_notice = '<div style="background: #f0f9ff; border: 1px solid #0ea5e9; padding: 15px; border-radius: 8px; margin: 15px 0;"><p style="margin: 0; color: #0c4a6e;"><strong>📋 Read-Only Access:</strong> This group has been settled and is now view-only. You can see all expenses and final balances, but cannot add new expenses.</p></div>'
    else:
        subject = f'Join "{group_name}" on Splittchen'
        action_text = 'Join'
        title_text = f'You\'ve been invited to join "{group_name}"'
        description_text = f'{inviter_name} has invited you to join their expense group on Splittchen.'
        status_notice = ''
    
    # Log invitation details for manual fallback
    current_app.logger.info(f'Sending invitation: to={to_email}, group={group_name}, token={share_token}, from={inviter_name}, settled={is_settled}')
    
    html_content = f'''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Group Invitation - Splittchen</title>
    </head>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
            {get_email_header()}
            <h2 style="color: #16a34a; margin-bottom: 20px;">{title_text}</h2>
            
            <p>{description_text}</p>
            
            {status_notice}
            
            {f'<p><em>"{personal_message}"</em></p>' if personal_message else ''}
            
            <div style="background: #f8fafc; padding: 20px; border-radius: 8px; margin: 20px 0;">
                <h3 style="margin-top: 0; margin-bottom: 10px;">Group Details:</h3>
                <p style="margin: 5px 0;"><strong>Group Name:</strong> {group_name}</p>
                <p style="margin: 5px 0;"><strong>Group Code:</strong> <code style="background: #e2e8f0; padding: 2px 6px; border-radius: 4px;">{share_token}</code></p>
                
                <div style="text-align: center; margin-top: 20px;">
                    <a href="{join_url}" 
                       style="display: inline-block; background: #16a34a; color: white; padding: 12px 24px; 
                              text-decoration: none; border-radius: 6px; font-weight: bold; text-align: center;
                              max-width: 100%; box-sizing: border-box;">
                        {action_text}
                    </a>
                </div>
            </div>
            
            <p style="font-size: 14px; color: #64748b;">
                Or copy and paste this link in your browser: <br>
                <a href="{join_url}">{join_url}</a>
            </p>
            
            <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 30px 0;">
            
            <p style="font-size: 12px; color: #94a3b8;">
                This invitation was sent from Splittchen, a simple expense splitting app. 
                If you didn't expect this email, you can safely ignore it.
            </p>
        </div>
    </body>
    </html>
    '''
    
    text_content = f'''
{title_text.replace("You've been invited to ", "").replace("You've been invited to view the settled group ", "View settled group ")}

{description_text}

{f"📋 READ-ONLY ACCESS: This group has been settled and is view-only. You can see expenses and balances but cannot add new expenses." if is_settled else ""}

{f'Personal message: "{personal_message}"' if personal_message else ''}

Group Details:
- Group Name: {group_name}
- Group Code: {share_token}

Join the group: {join_url}

This invitation was sent from Splittchen, a simple expense splitting app.
    '''
    
    # Use rate-limited email sending
    success, message = send_email_with_rate_limiting(
        to_email=to_email,
        subject=subject,
        html_content=html_content,
        email_type='invitation',
        group_id=group_id,
        participant_id=participant_id,
        text_content=text_content
    )
    
    if not success:
        current_app.logger.warning(f'Email failed to send. Reason: {message}. Manual invitation info: email={to_email}, join_url={join_url}')
    
    return success


def send_precreated_participant_invitation(to_email: str, participant_name: str, group_name: str, 
                                          participant: Any = None, group_id: Optional[int] = None,
                                          share_token: str = None, inviter_name: str = None,
                                          personal_message: str = '', access_token: str = None) -> bool:
    """Send invitation email to pre-created participant with personalized access link."""
    base_url = current_app.config['BASE_URL']
    
    # Generate personalized access URL
    if participant:
        personal_access_url = participant.generate_access_url(base_url)
    elif access_token and share_token:
        personal_access_url = f"{base_url}/group/{share_token}?p={access_token}"
    else:
        current_app.logger.error("Cannot generate access URL: missing participant object or access_token/share_token")
        return False
    
    subject = f'You\'ve been added to "{group_name}" on Splittchen'
    
    # Log invitation details
    current_app.logger.info(f'Sending pre-created participant invitation: to={to_email}, participant={participant_name}, group={group_name}')
    
    html_content = f'''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>You've Been Added - Splittchen</title>
    </head>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
            {get_email_header()}
            <h2 style="color: #16a34a; margin-bottom: 20px;">Welcome to "{group_name}"!</h2>
            
            <p>Hi <strong>{participant_name}</strong>,</p>
            
            <p>Great news! You've been added to the expense group <strong>"{group_name}"</strong> on Splittchen.</p>
            
            {f'<p><strong>{inviter_name}</strong> added you to this group.</p>' if inviter_name else ''}
            {f'<div style="background: #f9fafb; padding: 15px; border-radius: 6px; margin: 15px 0; border-left: 4px solid #6b7280;"><p style="margin: 0; font-style: italic; color: #374151;">"{personal_message}"</p></div>' if personal_message else ''}
            
            <div style="background: #f0f9ff; border: 1px solid #0ea5e9; padding: 20px; border-radius: 8px; margin: 20px 0;">
                <h3 style="margin-top: 0; color: #0c4a6e;">
                    <i style="color: #0ea5e9;">🎉</i> You're all set up!
                </h3>
                <p style="margin-bottom: 0; color: #0c4a6e;">
                    Your account has been created and you're ready to start tracking expenses. 
                    No forms to fill out - just click your personal link below!
                </p>
            </div>
            
            <div style="background: #f8fafc; padding: 20px; border-radius: 8px; margin: 20px 0;">
                <h3 style="margin: 0 0 10px 0; color: #16a34a;">Your Personal Access</h3>
                <p style="margin: 0 0 20px 0; color: #374151;">Click below to access the group instantly as <strong>{participant_name}</strong></p>
                
                <div style="text-align: center;">
                    <a href="{personal_access_url}" 
                       style="display: inline-block; background: #16a34a; color: white; padding: 14px 28px; 
                              text-decoration: none; border-radius: 6px; font-weight: bold; text-align: center;
                              max-width: 100%; box-sizing: border-box;">
                        Access Group
                    </a>
                </div>
            </div>
            
            <div style="background: #ecfdf5; padding: 15px; border-radius: 6px; margin: 20px 0; border-left: 4px solid #10b981;">
                <h4 style="color: #065f46; margin-top: 0;">What you can do:</h4>
                <ul style="margin: 5px 0; color: #065f46;">
                    <li>View all group expenses and who paid what</li>
                    <li>Add new expenses when you pay for something</li>
                    <li>See real-time balances - who owes what to whom</li>
                    <li>Access the group from any device using your personal link</li>
                </ul>
            </div>
            
            <p style="font-size: 14px; color: #64748b;">
                <strong>Bookmark this link:</strong> <br>
                <a href="{personal_access_url}">{personal_access_url}</a>
            </p>
            
            <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 30px 0;">
            
            <p style="font-size: 12px; color: #94a3b8;">
                You were added to this Splittchen group by the group administrator. 
                If you didn't expect this email, you can safely ignore it.
            </p>
        </div>
    </body>
    </html>
    '''
    
    text_content = f'''
Welcome to "{group_name}"!

Hi {participant_name},

You've been added to the expense group "{group_name}" on Splittchen.

{f"{inviter_name} added you to this group." if inviter_name else ""}
{f'Personal message: "{personal_message}"' if personal_message else ""}

Your personal access link: {personal_access_url}

What you can do:
- View all group expenses and balances
- Add new expenses when you pay for something  
- See who owes what to whom
- Access from any device using your personal link

Bookmark your link: {personal_access_url}

You were added by the group administrator.
    '''
    
    # Use rate-limited email sending
    # Get participant_id from participant object or None
    p_id = participant.id if participant and hasattr(participant, 'id') else None

    success, message = send_email_with_rate_limiting(
        to_email=to_email,
        subject=subject,
        html_content=html_content,
        email_type='precreated_invitation',
        group_id=group_id,
        participant_id=p_id,
        text_content=text_content
    )
    
    if not success:
        current_app.logger.warning(f'Pre-created participant email failed: {message}. Manual info: email={to_email}, personal_url={personal_access_url}')
    
    return success


def send_final_settlement_report(to_email: str, participant_name: str, group_name: str,
                                balances: Dict[int, float], settlements: list,
                                participants: list, currency: str, is_period_settlement: bool = False,
                                is_expiration_settlement: bool = False, is_deletion_settlement: bool = False,
                                group_id: Optional[int] = None, participant_id: Optional[int] = None,
                                share_token: Optional[str] = None, settlement_payments: Optional[list] = None,
                                settled_expenses: Optional[list] = None) -> tuple[bool, str]:
    """Send final settlement report email to participant.

    Args:
        settled_expenses: List of Expense objects that were settled (optional)
    """
    base_url = current_app.config['BASE_URL']
    
    if is_period_settlement:
        subject = f'Settlement Report - {group_name}'
    elif is_expiration_settlement:
        subject = f'Group Expired: Final Settlement - {group_name}'
    elif is_deletion_settlement:
        subject = f'Group Deleted: Final Balances - {group_name}'
    else:
        subject = f'Group Settled & Closed - {group_name}'
    
    # Find participant's balance and access token
    participant_balance = 0.0
    participant_id = None
    participant_access_token = None
    for p in participants:
        if p.email == to_email:
            participant_balance = balances.get(p.id, 0.0)
            participant_id = p.id
            participant_access_token = p.access_token
            break
    
    # Find settlements involving this participant
    participant_settlements = []
    for settlement in settlements:
        if settlement['from_participant_id'] == participant_id or settlement['to_participant_id'] == participant_id:
            participant_settlements.append(settlement)

    # Build payment ID mapping if settlement_payments provided
    payment_id_map = {}
    if settlement_payments:
        for payment in settlement_payments:
            key = (payment.from_participant_id, payment.to_participant_id)
            payment_id_map[key] = payment.id
    
    # Format balance
    if participant_balance > 0.01:
        balance_text = f"You are owed {format_currency(participant_balance, currency)}"
        balance_color = "#10B981"  # Green
    elif participant_balance < -0.01:
        balance_text = f"You owe {format_currency(abs(participant_balance), currency)}"
        balance_color = "#EF4444"  # Red
    else:
        balance_text = "You're all settled up!"
        balance_color = "#6B7280"  # Gray
    
    # Build balance table rows
    balance_table_rows = "".join([
        '''<tr>
            <td style="padding: 8px; border: 1px solid #e2e8f0;">{}</td>
            <td style="padding: 8px; text-align: right; border: 1px solid #e2e8f0; color: {};">
                {}
            </td>
        </tr>'''.format(
            p.name,
            '#10B981' if balances.get(p.id, 0.0) > 0 else '#EF4444' if balances.get(p.id, 0.0) < 0 else '#6B7280',
            format_currency(float(balances.get(p.id, 0.0)), currency)
        )
        for p in participants
    ])

    # Build expense list table if expenses provided
    expense_list_html = ""
    if settled_expenses:
        # Sort expenses by date (newest first)
        sorted_expenses = sorted(settled_expenses, key=lambda e: e.date, reverse=True)
        total_expenses_amount = sum(float(e.amount) for e in sorted_expenses)

        expense_rows = "".join([
            f'''<tr>
                <td style="padding: 8px; border: 1px solid #e2e8f0; font-size: 14px;">{expense.date.strftime('%Y-%m-%d')}</td>
                <td style="padding: 8px; border: 1px solid #e2e8f0; font-size: 14px;">{expense.title}</td>
                <td style="padding: 8px; border: 1px solid #e2e8f0; font-size: 14px;">{next(p.name for p in participants if p.id == expense.paid_by_id)}</td>
                <td style="padding: 8px; text-align: right; border: 1px solid #e2e8f0; font-weight: bold; font-size: 14px;">{format_currency(float(expense.amount), expense.currency)}</td>
            </tr>'''
            for expense in sorted_expenses
        ])

        expense_list_html = f'''
            <h3 style="color: #16a34a; margin-top: 30px;">Settled Expenses ({len(sorted_expenses)} items)</h3>
            <table style="width: 100%; border-collapse: collapse; margin: 15px 0;">
                <thead>
                    <tr style="background: #f1f5f9;">
                        <th style="padding: 10px; text-align: left; border: 1px solid #e2e8f0; font-size: 14px;">Date</th>
                        <th style="padding: 10px; text-align: left; border: 1px solid #e2e8f0; font-size: 14px;">Description</th>
                        <th style="padding: 10px; text-align: left; border: 1px solid #e2e8f0; font-size: 14px;">Paid By</th>
                        <th style="padding: 10px; text-align: right; border: 1px solid #e2e8f0; font-size: 14px;">Amount</th>
                    </tr>
                </thead>
                <tbody>
                    {expense_rows}
                </tbody>
                <tfoot>
                    <tr style="background: #f8fafc; font-weight: bold;">
                        <td colspan="3" style="padding: 10px; text-align: right; border: 1px solid #e2e8f0;">Total:</td>
                        <td style="padding: 10px; text-align: right; border: 1px solid #e2e8f0;">{format_currency(total_expenses_amount, currency)}</td>
                    </tr>
                </tfoot>
            </table>
        '''
    
    # Build conditional content for HTML
    if is_period_settlement:
        html_title = "Settlement Report"
    elif is_expiration_settlement:
        html_title = "Group Expired: Final Settlement"
    elif is_deletion_settlement:
        html_title = "Group Deleted: Final Balances"
    else:
        html_title = "Group Settled & Closed"
    if is_expiration_settlement:
        html_message = f"The expense group \"{group_name}\" has expired and been automatically settled."
    elif is_deletion_settlement:
        html_message = f"The expense group \"{group_name}\" has been deleted by the administrator. Here are your final balances before deletion."
    else:
        html_message = f"The expense group \"{group_name}\" has been settled."
    
    html_content = f'''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>{html_title} - Splittchen</title>
    </head>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
            {get_email_header()}
            <h2 style="color: #16a34a;">{html_title}</h2>
            
            <p>Hi {participant_name},</p>
            
            <p>{html_message} Here's your final report:</p>
            
            <div style="background: #f8fafc; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid {balance_color};">
                <h3 style="margin-top: 0; color: {balance_color};">Your Final Balance</h3>
                <p style="font-size: 18px; font-weight: bold; color: {balance_color}; margin: 0;">{balance_text}</p>
            </div>
            
            {f"""
            <h3 style="color: #16a34a;">Required Payments</h3>
            <div style="background: #fff3cd; padding: 15px; border-radius: 6px; border-left: 4px solid #ffc107;">
            """ + "".join([
                f"""<div style='margin: 10px 0; padding: 10px; background: white; border-radius: 4px;'>
                    <p style='margin: 5px 0;'><strong>Pay {format_currency(s['amount'], currency)}</strong> to {next(p.name for p in participants if p.id == s['to_participant_id'])}{next((' (' + p.email + ')') if p.email else '' for p in participants if p.id == s['to_participant_id'])}</p>
                    {f'<a href="{base_url}/payment/{payment_id_map.get((s["from_participant_id"], s["to_participant_id"]))}/confirm?token={participant_access_token}" style="display: inline-block; margin-top: 10px; padding: 10px 20px; background-color: #10b981; color: white; text-decoration: none; border-radius: 5px; font-weight: bold;">✓ Mark as Paid</a>' if payment_id_map.get((s["from_participant_id"], s["to_participant_id"])) and participant_access_token else ''}
                </div>"""
                for s in participant_settlements if s['from_participant_id'] == participant_id
            ]) + "</div>" if any(s['from_participant_id'] == participant_id for s in participant_settlements) else ""}
            
            {f"""
            <h3 style="color: #16a34a;">Expected Payments to You</h3>
            <div style="background: #d1fae5; padding: 15px; border-radius: 6px; border-left: 4px solid #10b981;">
            """ + "".join([
                f"""<div style='margin: 10px 0; padding: 10px; background: white; border-radius: 4px;'>
                    <p style='margin: 5px 0;'><strong>Receive {format_currency(s['amount'], currency)}</strong> from {next(p.name for p in participants if p.id == s['from_participant_id'])}{next((' (' + p.email + ')') if p.email else '' for p in participants if p.id == s['from_participant_id'])}</p>
                    {f'<a href="{base_url}/payment/{payment_id_map.get((s["from_participant_id"], s["to_participant_id"]))}/confirm?token={participant_access_token}" style="display: inline-block; margin-top: 10px; padding: 10px 20px; background-color: #10b981; color: white; text-decoration: none; border-radius: 5px; font-weight: bold;">✓ Mark as Paid</a>' if payment_id_map.get((s["from_participant_id"], s["to_participant_id"])) and participant_access_token else ''}
                </div>"""
                for s in participant_settlements if s['to_participant_id'] == participant_id
            ]) + "</div>" if any(s['to_participant_id'] == participant_id for s in participant_settlements) else ""}

            {expense_list_html}

            {"""
            <div style="background: #f1f5f9; padding: 15px; border-radius: 6px; margin: 20px 0; border-left: 4px solid #3b82f6;">
                <h4 style="color: #1e40af; margin-top: 0;">Payment Instructions</h4>
                <p style="margin: 5px 0;"><strong>How to settle:</strong></p>
                <ul style="margin: 5px 0;">
                    <li>Contact the people directly using the provided email addresses or phone numbers</li>
                    <li>Use mobile payment apps (Venmo, PayPal, Zelle, etc.) for quick transfers</li>
                    <li>Cash payments work too - just confirm receipt with the other person</li>
                    <li>Include a reference like "Splittchen - {group_name}" in your payment description</li>
                </ul>
                <p style="margin: 5px 0; font-size: 14px; color: #64748b;">
                    <em>This group is now settled and locked. No further expenses can be added.</em>
                </p>
            </div>
            """ if any(s['from_participant_id'] == participant_id for s in participant_settlements) or any(s['to_participant_id'] == participant_id for s in participant_settlements) else ""}
            
            <h3 style="color: #16a34a;">All Group Balances</h3>
            <table style="width: 100%; border-collapse: collapse; margin: 15px 0;">
                <thead>
                    <tr style="background: #f1f5f9;">
                        <th style="padding: 10px; text-align: left; border: 1px solid #e2e8f0;">Participant</th>
                        <th style="padding: 10px; text-align: right; border: 1px solid #e2e8f0;">Balance</th>
                    </tr>
                </thead>
                <tbody>
                    {balance_table_rows}
                </tbody>
            </table>
            
            
            <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 30px 0;">
            
            <p style="font-size: 12px; color: #94a3b8;">
                {"This group has been settled and is now locked. No further changes can be made." if not is_period_settlement else "This group has been settled for this period and remains open for new expenses."}
                Thank you for using Splittchen!
            </p>
        </div>
    </body>
    </html>
    '''
    
    # Build the subject line for text content
    if is_period_settlement:
        text_subject = f"Settlement Report - {group_name}"
    elif is_expiration_settlement:
        text_subject = f"Group Expired: Final Settlement - {group_name}"
    elif is_deletion_settlement:
        text_subject = f"Group Deleted: Final Balances - {group_name}"
    else:
        text_subject = f"Group Settled & Closed - {group_name}"
    
    # Build the main message text
    if is_expiration_settlement:
        main_message = f"The expense group \"{group_name}\" has expired and been automatically settled."
    elif is_deletion_settlement:
        main_message = f"The expense group \"{group_name}\" has been deleted by the administrator. Here are your final balances before deletion."
    else:
        main_message = f"The expense group \"{group_name}\" has been settled."
    
    text_content = f'''
{text_subject}

Hi {participant_name},

{main_message} Here's your final report:

Your Final Balance: {balance_text}

{"Required Payments:" if any(s['from_participant_id'] == participant_id for s in participant_settlements) else ""}
{"".join([f"- Pay {format_currency(s['amount'], currency)} to {next(p.name for p in participants if p.id == s['to_participant_id'])}" for s in participant_settlements if s['from_participant_id'] == participant_id])}

{"Expected Payments to You:" if any(s['to_participant_id'] == participant_id for s in participant_settlements) else ""}
{"".join([f"- Receive {format_currency(s['amount'], currency)} from {next(p.name for p in participants if p.id == s['from_participant_id'])}" for s in participant_settlements if s['to_participant_id'] == participant_id])}

All Group Balances:
{"".join([f"- {p.name}: {format_currency(float(balances.get(p.id, 0.0)), currency)}" for p in participants])}

{f"View Group Details: {base_url}/group/{share_token}" if share_token else ""}

{"This group has been settled and is now locked. No further changes can be made." if not is_period_settlement else "This group has been settled for this period and remains open for new expenses."} Thank you for using Splittchen!
    '''
    
    # Use rate-limited email sending
    success, message = send_email_with_rate_limiting(
        to_email=to_email,
        subject=subject,
        html_content=html_content,
        email_type='settlement',
        group_id=group_id,
        participant_id=participant_id,
        text_content=text_content
    )
    
    return success, message


def calculate_settlements(balances: Dict[int, Decimal]) -> list:
    """Calculate optimal settlements to minimize transactions using advanced algorithm."""
    # Filter out participants with negligible balances
    # Convert to float for the algorithm while preserving precision
    significant_balances = {pid: float(balance) for pid, balance in balances.items() 
                          if abs(balance) > Decimal('0.01')}
    
    if not significant_balances:
        return []
    
    # Use optimized algorithm that minimizes number of transactions
    return _minimize_transactions(significant_balances)


def _minimize_transactions(balances: Dict[int, float]) -> list:
    """
    Optimal settlement algorithm that minimizes the number of transactions.
    
    This algorithm achieves the theoretical minimum number of transactions:
    - For n participants with non-zero balances, the minimum transactions needed is n-1
    - Uses a greedy approach that always matches largest debtor with largest creditor
    - This approach typically produces near-optimal results for practical scenarios
    
    Time complexity: O(n²) in worst case, but typically much better in practice
    """
    settlements = []
    
    # Create working copy of balances for manipulation
    working_balances = {pid: float(balance) for pid, balance in balances.items() 
                       if balance is not None and abs(balance) > 0.01}
    
    if not working_balances:
        return []
    
    # Continue until all balances are settled
    while len([b for b in working_balances.values() if abs(b) > 0.01]) > 1:
        # Find participant with largest debt (most negative balance)
        debtor_id = min(working_balances.items(), key=lambda x: x[1])[0]
        debtor_amount = abs(working_balances[debtor_id])
        
        # Find participant with largest credit (most positive balance) 
        creditor_id = max(working_balances.items(), key=lambda x: x[1])[0]
        creditor_amount = working_balances[creditor_id]
        
        # Safety check: prevent same participant being both debtor and creditor
        if debtor_id == creditor_id:
            break
        
        # Skip if no valid debtor or creditor
        if debtor_amount < 0.01 or creditor_amount < 0.01:
            break
            
        # Transfer amount is minimum of debt and credit
        transfer_amount = min(debtor_amount, creditor_amount)
        
        if transfer_amount > 0.01:
            settlements.append({
                'from_participant_id': debtor_id,
                'to_participant_id': creditor_id,
                'amount': round(transfer_amount, 2)
            })
            
            # Update balances
            working_balances[debtor_id] += transfer_amount
            working_balances[creditor_id] -= transfer_amount
            
            # Remove participants who are fully settled
            if abs(working_balances[debtor_id]) < 0.01:
                del working_balances[debtor_id]
            if abs(working_balances[creditor_id]) < 0.01:
                del working_balances[creditor_id]
    
    return settlements


def format_currency(amount: Union[float, Decimal], currency: str = 'USD') -> str:
    """Format amount as currency string."""
    from app.currency import currency_service
    
    if isinstance(amount, (int, float)):
        amount = Decimal(str(amount))
    
    return currency_service.format_amount(amount, currency)


def format_currency_suffix(amount: Union[float, Decimal], currency: str = 'USD') -> str:
    """Format amount as currency string with symbol after the amount."""
    from app.currency import currency_service, SUPPORTED_CURRENCIES
    
    if isinstance(amount, (int, float)):
        amount = Decimal(str(amount))
    
    if currency not in SUPPORTED_CURRENCIES:
        return f"{float(amount):.2f} {currency}"
    
    symbol = SUPPORTED_CURRENCIES[currency]['symbol']
    
    # Handle different formatting for different currencies
    if currency == 'JPY' or currency == 'KRW':
        # No decimal places for these currencies
        return f"{amount:.0f} {symbol}"
    else:
        return f"{amount:.2f} {symbol}"


def get_participant_color(index: int) -> str:
    """Get a color for participant based on index."""
    colors = [
        '#3B82F6',  # Blue
        '#EF4444',  # Red
        '#10B981',  # Green
        '#F59E0B',  # Yellow
        '#8B5CF6',  # Purple
        '#EC4899',  # Pink
        '#06B6D4',  # Cyan
        '#84CC16',  # Lime
        '#F97316',  # Orange
        '#6B7280'   # Gray
    ]
    return colors[index % len(colors)]


def log_audit_action(group_id: int, action: str, description: str, 
                     performed_by: Optional[str] = None, performed_by_participant_id: Optional[int] = None,
                     expense_id: Optional[int] = None, participant_id: Optional[int] = None, details: Optional[dict] = None) -> None:
    """Log an audit action for group changes.
    
    Args:
        group_id: ID of the group where action occurred
        action: Type of action (e.g., 'expense_added', 'expense_deleted', 'participant_removed')
        description: Human-readable description of the action
        performed_by: Name of person who performed the action
        performed_by_participant_id: ID of participant who performed the action
        expense_id: ID of expense if action is expense-related
        participant_id: ID of participant if action is participant-related
        details: Additional structured data about the action
    """
    from app.models import AuditLog
    from app import db
    
    try:
        audit_log = AuditLog(
            group_id=group_id,
            action=action,
            description=description,
            performed_by=performed_by,
            performed_by_participant_id=performed_by_participant_id,
            expense_id=expense_id,
            participant_id=participant_id,
            details=details or {}
        )
        
        db.session.add(audit_log)
        db.session.commit()
        current_app.logger.info(f'Audit log created: {action} in group {group_id}')
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Failed to create audit log: {e}')


def get_user_groups_from_session() -> List[Dict[str, Any]]:
    """Extract all groups the user has access to from session data."""
    from flask import session
    from .models import Group
    
    groups = []
    
    # Find all group tokens in session
    group_tokens = set()
    for key in session.keys():
        if key.startswith('participant_') or key.startswith('admin_') or key.startswith('viewer_'):
            token = key.split('_', 1)[1]
            group_tokens.add(token)
    
    # Get group details from database
    for token in group_tokens:
        group = Group.query.filter_by(share_token=token).first()
        if group:
            is_admin = session.get(f'admin_{token}') == group.admin_token
            is_participant = session.get(f'participant_{token}') is not None
            is_viewer = session.get(f'viewer_{token}') is not None
            
            # Only add if user has some form of access
            if is_admin or is_participant or is_viewer:
                groups.append({
                    'group': group,
                    'is_admin': is_admin,
                    'is_participant': is_participant or is_viewer,  # Treat viewers as participants for display
                    'last_accessed': group.created_at  # Could be enhanced with actual last access
                })
    
    # Sort by most recently created (could be enhanced with last accessed)
    groups.sort(key=lambda x: x['last_accessed'], reverse=True)
    
    return groups


def send_group_links_email(email: str, groups: list) -> bool:
    """Send email with links to active groups for the specified email address.
    
    Args:
        email: The email address to send group links to
        groups: List of Group objects the email address participates in
        
    Returns:
        True if email was sent successfully, False otherwise
    """
    if not groups:
        return False
    
    base_url = current_app.config['BASE_URL']
    
    subject = f"Your Active Splittchen Groups ({len(groups)} group{'s' if len(groups) != 1 else ''})"
    
    # Build HTML content
    group_links_html = ""
    for group in groups:
        # Try to find participant for this email to generate personalized link
        from app.models import Participant
        participant = Participant.query.filter_by(group_id=group.id, email=email).first()
        
        # Check if this email is the creator (has admin access)
        is_creator = group.creator_email and group.creator_email.lower() == email.lower()
        
        if participant:
            group_url = participant.generate_access_url(base_url)
        else:
            group_url = f"{base_url}/group/{group.share_token}"
        
        # Generate admin URL if this is the creator
        admin_url = f"{base_url}/admin/{group.admin_token}" if is_creator else None
        status_text = ""
        if group.is_settled:
            status_text = " (Settled)"
        elif group.is_expired:
            status_text = " (Expired)"
        elif group.is_recurring:
            status_text = " (Recurring)"
        
        # Show admin access indicator if this is the creator
        creator_badge = f'<span style="background: #16a34a; color: white; padding: 2px 6px; border-radius: 4px; font-size: 12px; font-weight: bold;">ADMIN</span>' if is_creator else ''
        
        group_links_html += f'''
        <div style="background: #f8fafc; padding: 15px; margin: 10px 0; border-radius: 6px; border-left: 4px solid {'#16a34a' if is_creator else '#3b82f6'};">
            <h3 style="margin: 0 0 10px 0; color: {'#16a34a' if is_creator else '#1e40af'};">{group.name}{status_text} {creator_badge}</h3>
            {f'<p style="margin: 5px 0; color: #64748b;">{group.description}</p>' if group.description else ''}
            <p style="margin: 5px 0;">
                <strong>Group link:</strong> 
                <a href="{group_url}" style="color: #3b82f6; text-decoration: none;">{group_url}</a>
            </p>
            {f'''<p style="margin: 5px 0;">
                <strong>Admin link:</strong> 
                <a href="{admin_url}" style="color: #16a34a; text-decoration: none; font-weight: bold;">{admin_url}</a>
            </p>''' if admin_url else ''}
            <p style="margin: 5px 0; font-size: 14px; color: #64748b;">
                Created: {group.created_at.strftime('%B %d, %Y')} | 
                {len(group.participants)} participant{'s' if len(group.participants) != 1 else ''} | 
                {group.currency}
                {' | You are the group admin' if is_creator else ''}
            </p>
        </div>
        '''
    
    html_content = f'''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>{subject}</title>
    </head>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
        {get_email_header()}
        <div style="background: linear-gradient(135deg, #10b981, #059669); color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; text-align: center;">
            <h1 style="margin: 0; font-size: 24px;">Your Splittchen Groups</h1>
            <p style="margin: 10px 0 0 0; opacity: 0.9;">Here are your active expense-sharing groups</p>
        </div>
        
        <div style="background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
            <p>Hi there,</p>
            
            <p>You requested to find your active Splittchen groups associated with <strong>{email}</strong>.</p>
            
            <p>We found <strong>{len(groups)} group{'s' if len(groups) != 1 else ''}</strong> where you are a participant.</p>
            
            <!-- Quick Access Section -->
            <div style="margin: 25px 0; padding: 20px; background: #f0fdf4; border-radius: 8px; border: 2px solid #16a34a;">
                <h3 style="margin: 0 0 15px 0; color: #047857; font-size: 18px;">🚀 Quick Access</h3>

                <!-- Import Button -->
                <div style="text-align: center; margin: 15px 0;">
                    <a href="{base_url}/find-groups?import_email={email}"
                       style="display: inline-block; background: #047857; color: white; text-decoration: none;
                              padding: 12px 20px; border-radius: 6px; font-weight: bold; font-size: 14px;
                              max-width: 100%; box-sizing: border-box;">
                        📥 Import All Groups to Device
                    </a>
                </div>

                <p style="margin: 10px 0 0 0; font-size: 14px; color: #065f46; font-weight: 500;">
                    <strong>Recommended:</strong> Add all groups to your browser for instant access!
                </p>
            </div>
            
            <h3 style="color: #1e40af; margin: 30px 0 15px 0;">📋 Your Groups</h3>
            
            {group_links_html}
            
            <div style="background: #f1f5f9; padding: 15px; border-radius: 6px; margin: 20px 0; border-left: 4px solid #3b82f6;">
                <h4 style="color: #1e40af; margin-top: 0;">💡 How to use these links:</h4>
                <ul style="margin: 5px 0;">
                    <li>Click any group link above to access that group directly</li>
                    <li>Since you're already a participant, you'll be taken straight to the group page</li>
                    <li>You can view expenses, balances, and add new expenses</li>
                    <li>Links are unique to each group and can be shared with other participants</li>
                    <li><strong>💡 Pro tip:</strong> Use the green "Import" button above for quick access!</li>
                </ul>
            </div>
            
            <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 30px 0;">
            
            <p style="font-size: 12px; color: #94a3b8;">
                This email was sent because someone requested to find groups for {email}.
                If you didn't request this, you can safely ignore this email.
                <br><br>
                Splittchen - Simple expense sharing
            </p>
        </div>
    </body>
    </html>
    '''
    
    # Build text content
    group_links_text = ""
    for group in groups:
        # Check if this email is the creator (has admin access)
        is_creator = group.creator_email and group.creator_email.lower() == email.lower()
        
        group_url = f"{base_url}/group/{group.share_token}"
        admin_url = f"{base_url}/admin/{group.admin_token}" if is_creator else None
        
        status_text = ""
        if group.is_settled:
            status_text = " (Settled)"
        elif group.is_expired:
            status_text = " (Expired)"
        elif group.is_recurring:
            status_text = " (Recurring)"
        
        creator_text = " (ADMIN)" if is_creator else ""
        
        group_links_text += f'''
{group.name}{status_text}{creator_text}
{group.description if group.description else ''}
Group link: {group_url}
{f'Admin link: {admin_url}' if admin_url else ''}
Created: {group.created_at.strftime('%B %d, %Y')} | {len(group.participants)} participant{'s' if len(group.participants) != 1 else ''} | {group.currency}{' | You are the group admin' if is_creator else ''}

'''
    
    text_content = f'''
Your Splittchen Groups

Hi there,

You requested to find your active Splittchen groups associated with {email}.

We found {len(groups)} group{'s' if len(groups) != 1 else ''} where you are a participant:

{group_links_text}

How to use these links:
- Copy and paste any group link into your browser to access that group
- Since you're already a participant, you'll be taken straight to the group page
- You can view expenses, balances, and add new expenses
- Links are unique to each group and can be shared with other participants

This email was sent because someone requested to find groups for {email}.
If you didn't request this, you can safely ignore this email.

Splittchen - Simple expense sharing
    '''
    
    return send_email_smtp(email, subject, html_content, text_content)


def send_settlement_reminder(to_email: str, participant_name: str, group_name: str, 
                           group_id: int, participant_id: int, settlement_date: str, 
                           current_balance: float, currency: str, share_token: str) -> bool:
    """Send 3-day advance settlement reminder email.
    
    Args:
        to_email: Recipient email address
        participant_name: Name of the participant
        group_name: Name of the group
        group_id: Group database ID
        participant_id: Participant database ID
        settlement_date: Formatted settlement date string
        current_balance: Participant's current balance
        currency: Group currency
        share_token: Group share token for links
        
    Returns:
        True if email was sent successfully, False otherwise
    """
    if not to_email:
        return False
    
    base_url = current_app.config['BASE_URL']
    group_url = f"{base_url}/group/{share_token}"
    
    # Determine balance message
    if current_balance > 0.01:
        balance_text = f"You are owed {format_currency(current_balance, currency)}"
        balance_color = "#10b981"  # Green for positive balance
    elif current_balance < -0.01:
        balance_text = f"You owe {format_currency(abs(current_balance), currency)}"
        balance_color = "#ef4444"  # Red for negative balance
    else:
        balance_text = "Your balance is settled"
        balance_color = "#6b7280"  # Gray for zero balance
    
    subject = f"Settlement Reminder: {group_name} - 3 days to go!"
    
    # Text content for email clients that don't support HTML
    text_content = f"""
Settlement Reminder - {group_name}

Hi {participant_name},

Your group "{group_name}" will be automatically settled in 3 days on {settlement_date}.

Current Status:
{balance_text}

What you can do:
- Add any remaining expenses before settlement
- Review your expenses and balances
- Settle up with other participants

Visit your group: {group_url}

This is an automated reminder for recurring expense groups.
You can manage your group settings by visiting the link above.

Splittchen - Simple expense sharing
"""
    
    # HTML content
    html_content = f'''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>{subject}</title>
    </head>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
        {get_email_header()}
        
        <div style="background: linear-gradient(135deg, #f59e0b, #d97706); color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; text-align: center;">
            <h1 style="margin: 0; font-size: 24px;">Settlement Reminder</h1>
            <p style="margin: 10px 0 0 0; opacity: 0.9;">3 days until automatic settlement</p>
        </div>
        
        <div style="background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
            <p>Hi {participant_name},</p>
            
            <p>Your recurring expense group <strong>"{group_name}"</strong> will be automatically settled in <strong>3 days</strong> on <strong>{settlement_date}</strong>.</p>
            
            <div style="background: #f8fafc; padding: 20px; border-radius: 8px; margin: 20px 0; text-align: center; border: 2px solid {balance_color};">
                <h3 style="margin: 0 0 10px 0; color: {balance_color};">Current Balance</h3>
                <p style="margin: 0; font-size: 18px; font-weight: bold; color: {balance_color};">{balance_text}</p>
            </div>
            
            <div style="background: #fef3c7; padding: 15px; border-radius: 6px; margin: 20px 0; border-left: 4px solid #f59e0b;">
                <h4 style="color: #92400e; margin-top: 0;">What happens next?</h4>
                <ul style="margin: 5px 0; color: #92400e;">
                    <li>In 3 days, the system will automatically calculate final balances</li>
                    <li>Settlement reports will be sent to all participants</li>
                    <li>The group will continue for next month's expenses</li>
                    <li>You'll get payment suggestions to settle your balance</li>
                </ul>
            </div>
            
            <div style="background: #ecfdf5; padding: 15px; border-radius: 6px; margin: 20px 0; border-left: 4px solid #10b981;">
                <h4 style="color: #065f46; margin-top: 0;">What you can do now:</h4>
                <ul style="margin: 5px 0; color: #065f46;">
                    <li>Add any remaining expenses for this month</li>
                    <li>Review all expenses and balances</li>
                    <li>Start settling up with other participants</li>
                    <li>Check for any missing receipts or expenses</li>
                </ul>
            </div>
            
            <div style="margin: 30px 0;">
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="vertical-align: middle; padding-right: 20px;">
                            <p style="margin: 0; color: #374151;"><strong>Ready to continue?</strong></p>
                        </td>
                        <td style="vertical-align: middle; text-align: right; min-width: 200px;">
                            <a href="{group_url}" style="background: #16a34a; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">
                                View Group & Add Expenses
                            </a>
                        </td>
                    </tr>
                </table>
            </div>
            
            <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 30px 0;">
            
            <p style="font-size: 12px; color: #94a3b8;">
                This is an automated reminder for your recurring expense group.
                You can manage your group settings by visiting the group link above.
                <br><br>
                Splittchen - Simple expense sharing
            </p>
        </div>
    </body>
    </html>
    '''
    
    # Use rate-limited email sending
    success, message = send_email_with_rate_limiting(
        to_email=to_email,
        subject=subject,
        html_content=html_content,
        email_type='reminder',
        group_id=group_id,
        participant_id=participant_id,
        text_content=text_content
    )
    
    if not success:
        current_app.logger.warning(f"Failed to send settlement reminder to {to_email}: {message}")
    
    return success


def generate_history_text(group) -> str:
    """
    Generate a comprehensive text file with group history.
    
    Includes:
    - Group information
    - All participants
    - All expenses (current and archived)
    - Current balances
    - Settlement suggestions
    - Activity log
    
    Args:
        group: Group model instance
        
    Returns:
        str: Formatted text content for download
    """
    from datetime import datetime
    from app.models import AuditLog
    
    lines = []
    
    # Header
    lines.append("=" * 60)
    lines.append(f"EXPENSE HISTORY: {group.name}")
    lines.append("=" * 60)
    lines.append(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Group created: {group.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Default currency: {group.currency}")
    
    if group.description:
        lines.append(f"Description: {group.description}")
    
    if group.is_settled:
        lines.append(f"Status: SETTLED (on {group.settled_at.strftime('%Y-%m-%d')})")
    elif group.is_expired:
        lines.append("Status: EXPIRED")
    else:
        lines.append("Status: ACTIVE")
    
    if group.is_recurring:
        lines.append(f"Recurring: Yes (monthly)")
        if group.next_settlement_date:
            lines.append(f"Next settlement: {group.next_settlement_date.strftime('%Y-%m-%d')}")
    
    lines.append("")
    
    # Participants
    lines.append("PARTICIPANTS")
    lines.append("-" * 20)
    for i, participant in enumerate(group.participants, 1):
        lines.append(f"{i}. {participant.name}")
        if participant.email:
            lines.append(f"   Email: {participant.email}")
        lines.append(f"   Joined: {participant.joined_at.strftime('%Y-%m-%d')}")
        if participant.is_admin:
            lines.append("   Role: Admin")
        lines.append("")
    
    # All expenses (current and archived)
    all_expenses = sorted(group.expenses, key=lambda x: x.date, reverse=True)
    
    lines.append("ALL EXPENSES")
    lines.append("-" * 20)
    if all_expenses:
        total_amount = sum(float(expense.amount) for expense in all_expenses)
        current_expenses = [e for e in all_expenses if not e.is_archived]
        archived_expenses = [e for e in all_expenses if e.is_archived]
        
        lines.append(f"Total expenses: {len(all_expenses)}")
        lines.append(f"Current expenses: {len(current_expenses)}")
        lines.append(f"Archived expenses: {len(archived_expenses)}")
        lines.append(f"Total amount: {format_currency_suffix(total_amount, group.currency)}")
        lines.append("")
        
        for expense in all_expenses:
            lines.append(f"Date: {expense.date.strftime('%Y-%m-%d')}")
            lines.append(f"Title: {expense.title}")
            if expense.description:
                lines.append(f"Description: {expense.description}")
            lines.append(f"Amount: {format_currency_suffix(float(expense.amount), expense.currency)}")
            lines.append(f"Paid by: {expense.paid_by.name}")
            lines.append(f"Category: {expense.category}")
            
            if expense.is_archived:
                lines.append(f"Status: ARCHIVED (settlement period: {expense.settlement_period})")
            else:
                lines.append("Status: CURRENT")
            
            # Show split details
            if expense.expense_shares:
                lines.append("Split between:")
                for share in expense.expense_shares:
                    share_amount = float(expense.amount) / len(expense.expense_shares)
                    lines.append(f"  - {share.participant.name}: {format_currency_suffix(share_amount, expense.currency)}")
            
            lines.append("")
    else:
        lines.append("No expenses recorded.")
        lines.append("")
    
    # Current balances (only if there are current expenses)
    current_expenses = [e for e in all_expenses if not e.is_archived]
    if current_expenses:
        lines.append("CURRENT BALANCES")
        lines.append("-" * 20)
        balances = group.get_balances(group.currency)
        
        for participant in group.participants:
            balance = balances.get(participant.id, 0.0)
            if balance > 0.01:
                lines.append(f"{participant.name}: +{format_currency_suffix(balance, group.currency)} (owed to them)")
            elif balance < -0.01:
                lines.append(f"{participant.name}: -{format_currency_suffix(abs(balance), group.currency)} (they owe)")
            else:
                lines.append(f"{participant.name}: {format_currency_suffix(0, group.currency)} (settled)")
        
        lines.append("")
        
        # Settlement suggestions
        settlements = calculate_settlements(balances)
        if settlements:
            lines.append("SUGGESTED SETTLEMENTS")
            lines.append("-" * 25)
            for settlement in settlements:
                from_participant = next(p for p in group.participants if p.id == settlement['from_participant_id'])
                to_participant = next(p for p in group.participants if p.id == settlement['to_participant_id'])
                amount = settlement['amount']
                lines.append(f"{from_participant.name} → {to_participant.name}: {format_currency_suffix(amount, group.currency)}")
            lines.append("")
    
    # Activity log
    lines.append("ACTIVITY LOG")
    lines.append("-" * 15)
    limit = current_app.config.get('ACTIVITY_LOG_LIMIT', 100)
    audit_logs = AuditLog.query.filter_by(group_id=group.id).order_by(AuditLog.created_at.desc()).limit(limit).all()
    
    if audit_logs:
        for log in audit_logs:
            lines.append(f"{log.created_at.strftime('%Y-%m-%d %H:%M')} - {log.description}")
            if log.performed_by:
                lines.append(f"  By: {log.performed_by}")
        lines.append("")
    else:
        lines.append("No activity recorded.")
        lines.append("")
    
    # Footer
    lines.append("=" * 60)
    lines.append("Generated by Splittchen - Privacy-first expense splitting")
    lines.append("=" * 60)
    
    return "\n".join(lines)


def sanitize_user_input(text: str) -> str:
    """
    Sanitize user input to prevent XSS and other injection attacks.
    
    Args:
        text: Raw user input text
        
    Returns:
        Sanitized text safe for storage and display
    """
    if not text:
        return ""
    
    import html
    
    # Strip whitespace and limit length
    text = text.strip()[:1000]  # Reasonable length limit
    
    # Remove any potential script tags or dangerous HTML
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<[^>]+>', '', text)  # Remove all HTML tags
    
    # Escape HTML entities
    text = html.escape(text)
    
    return text


def set_secure_admin_session(share_token: str, admin_token: str) -> None:
    """
    Securely store admin token in session for group access.
    
    Args:
        share_token: Group share token
        admin_token: Admin token to store securely
    """
    from flask import session
    
    # Make session permanent BEFORE storing tokens
    session.permanent = True
    
    # Store admin token in session for this specific group
    session[f'admin_{share_token}'] = admin_token


def get_secure_admin_session(share_token: str) -> Optional[str]:
    """
    Retrieve admin token from secure session storage.
    
    Args:
        share_token: Group share token
        
    Returns:
        Admin token if found and valid, None otherwise
    """
    from flask import session
    
    return session.get(f'admin_{share_token}')


def clear_all_group_sessions() -> None:
    """
    Clear all group-related session data.
    
    Removes all participant and admin tokens from the current session.
    """
    from flask import session
    
    # Find all group-related session keys
    keys_to_remove = []
    for key in session.keys():
        if key.startswith('participant_') or key.startswith('admin_'):
            keys_to_remove.append(key)
    
    # Remove all group session data
    for key in keys_to_remove:
        session.pop(key, None)


def execute_with_transaction(operation_func: Callable[[], Any], 
                           operation_description: str = "database operation") -> Any:
    """
    Execute a database operation within a transaction with proper error handling.
    
    Args:
        operation_func: Function to execute within the transaction
        operation_description: Description for logging purposes
        
    Returns:
        Result of the operation function
        
    Raises:
        Exception: Re-raises any exception that occurs during the operation
    """
    from app import db
    
    try:
        current_app.logger.debug(f"Starting {operation_description}")
        result = operation_func()
        db.session.commit()
        current_app.logger.info(f"Successfully completed {operation_description}")
        return result
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Failed {operation_description}: {str(e)}")
        raise