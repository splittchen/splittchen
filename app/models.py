"""Database models for Splittchen application."""

import secrets
import string
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, List, Any
from decimal import Decimal

from flask import current_app
from app import db


def generate_token(length: int = 8) -> str:
    """Generate a random alphanumeric token.
    
    Uses cryptographically secure random number generator.
    Character set: A-Z, 0-9 (36 characters)
    
    Security analysis for 12-character tokens:
    - Total combinations: 4.74 × 10^18
    - Collision probability with 1M groups: < 0.00001%
    """
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def get_default_currency() -> str:
    """Get the default currency from app config, fallback to USD."""
    try:
        return current_app.config.get('DEFAULT_CURRENCY', 'USD')
    except RuntimeError:
        # Outside application context, use fallback
        return 'USD'


class Group(db.Model):
    """Expense group model."""
    __tablename__ = 'groups'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    share_token = db.Column(db.String(16), unique=True, nullable=False, default=lambda: generate_token(12), index=True)
    admin_token = db.Column(db.String(40), unique=True, nullable=False, default=lambda: generate_token(32), index=True)
    creator_email = db.Column(db.String(120))  # Email of the group creator for admin access recovery
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    is_settled = db.Column(db.Boolean, default=False, nullable=False, index=True)
    settled_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    expires_at = db.Column(db.DateTime)
    
    # Currency settings - keeping both for backward compatibility during migration
    default_currency = db.Column(db.String(3), default=get_default_currency, nullable=False)  # Group's preferred currency
    base_currency = db.Column(db.String(3), default=get_default_currency, nullable=False)    # Currency for calculations (same as default_currency)
    
    @property
    def currency(self) -> str:
        """Get the group's currency (uses default_currency)."""
        return self.default_currency
    
    @currency.setter
    def currency(self, value: str) -> None:
        """Set the group's currency (updates both default_currency and base_currency)."""
        self.default_currency = value
        self.base_currency = value
    
    # Recurring settlement settings
    is_recurring = db.Column(db.Boolean, default=False, nullable=False)  # Enable auto-settlements
    recurrence_type = db.Column(db.String(20), default=None)  # 'monthly', 'weekly', etc.
    next_settlement_date = db.Column(db.DateTime)  # When next auto-settlement should occur
    
    # Relationships
    participants = db.relationship('Participant', back_populates='group', cascade='all, delete-orphan')
    expenses = db.relationship('Expense', back_populates='group', cascade='all, delete-orphan')
    
    def __init__(self, name: str, description: Optional[str] = None, 
                 expires_at: Optional[datetime] = None, currency: str = 'USD',
                 is_recurring: bool = False, recurrence_type: Optional[str] = None,
                 creator_email: Optional[str] = None, **kwargs):
        """Initialize Group instance."""
        super().__init__(**kwargs)
        self.name = name
        self.description = description
        self.expires_at = expires_at
        # Use the property setter to set both currencies
        self.currency = currency
        self.is_recurring = is_recurring
        self.recurrence_type = recurrence_type
        self.creator_email = creator_email
    
    def __repr__(self) -> str:
        return f'<Group {self.name}>'
    
    def set_next_settlement_date(self) -> None:
        """Set next settlement date for recurring groups to end of current/next month."""
        if not self.is_recurring:
            return
            
        from datetime import date, time
        import calendar
        
        today = date.today()
        # Set next settlement to last day of current month at 23:59
        last_day = calendar.monthrange(today.year, today.month)[1]
        next_settlement = date(today.year, today.month, last_day)
        
        # If we're already past the last day of this month, move to next month
        if today >= next_settlement:
            if today.month == 12:
                next_settlement = date(today.year + 1, 1, 31)
                if next_settlement.month != 1:  # Handle February case
                    next_settlement = date(today.year + 1, 2, 28)
            else:
                next_month = today.month + 1
                last_day_next = calendar.monthrange(today.year, next_month)[1]
                next_settlement = date(today.year, next_month, last_day_next)
        
        # Create datetime for 23:59 on the settlement date
        settlement_time = time(hour=23, minute=59)
        self.next_settlement_date = datetime.combine(next_settlement, settlement_time)
    
    @property
    def is_expired(self) -> bool:
        """Check if group has expired."""
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at.replace(tzinfo=timezone.utc)
    
    @property
    def member_count(self) -> int:
        """Get number of participants in group."""
        return len(self.participants)
    
    def get_balances(self, display_currency: Optional[str] = None) -> Dict[int, Decimal]:
        """Calculate current balances for all participants."""
        from decimal import Decimal
        balances = {p.id: Decimal('0.0') for p in self.participants}
        
        # Use group's currency if none specified
        if display_currency is None:
            display_currency = self.currency
        
        for expense in self.expenses:
            # Skip archived expenses - they are part of settlement history
            if expense.is_archived:
                continue
            # Calculate amounts in display currency
            from app.currency import currency_service
            
            # Convert from group currency to display currency
            converted_paid = currency_service.convert_amount(
                expense.amount, self.currency, display_currency
            )
            if converted_paid is None:
                # Fallback to base currency amount if conversion fails
                converted_paid = expense.amount
            
            # Subtract amount paid by participant
            if expense.paid_by_id in balances:
                balances[expense.paid_by_id] += converted_paid
            
            # Add amount owed by each participant (split equally for now)
            share_count = Decimal(len(expense.expense_shares))  # type: ignore
            share_amount = converted_paid / share_count
            for share in expense.expense_shares:  # type: ignore
                balances[share.participant_id] -= share_amount
                
        return balances
    
    def delete_group(self):
        """
        Permanently delete this group and all associated data.

        This is a destructive operation that cannot be undone.
        Deletes in proper order to respect foreign key constraints:
        1. EmailLog entries (reference participants and groups)
        2. AuditLog entries (reference participants, expenses, and groups)
        3. SettlementPayment entries (reference participants and settlement periods)
        4. ExpenseShare entries (via cascade from Expense deletion)
        5. Expense entries (reference participants via paid_by_id)
        6. Participant entries
        7. SettlementPeriod entries
        8. Group entry

        Returns:
            dict: Summary of deleted records
        """
        deleted_summary = {
            'email_logs': 0,
            'audit_logs': 0,
            'settlement_payments': 0,
            'expense_shares': 0,
            'expenses': 0,
            'participants': 0,
            'settlement_periods': 0,
            'group_name': self.name
        }

        # Count records before deletion for summary (without loading objects into session)
        deleted_summary['email_logs'] = EmailLog.query.filter_by(group_id=self.id).count()
        deleted_summary['audit_logs'] = AuditLog.query.filter_by(group_id=self.id).count()
        deleted_summary['settlement_periods'] = SettlementPeriod.query.filter_by(group_id=self.id).count()
        deleted_summary['participants'] = Participant.query.filter_by(group_id=self.id).count()
        deleted_summary['expenses'] = Expense.query.filter_by(group_id=self.id).count()

        # Count settlement payments and expense shares
        from app.models import SettlementPayment, ExpenseShare
        period_ids = [p[0] for p in db.session.query(SettlementPeriod.id).filter_by(group_id=self.id).all()]
        expense_ids = [e[0] for e in db.session.query(Expense.id).filter_by(group_id=self.id).all()]

        if period_ids:
            deleted_summary['settlement_payments'] = SettlementPayment.query.filter(
                SettlementPayment.settlement_period_id.in_(period_ids)
            ).count()

        if expense_ids:
            deleted_summary['expense_shares'] = ExpenseShare.query.filter(
                ExpenseShare.expense_id.in_(expense_ids)
            ).count()

        try:
            # Use bulk delete operations to avoid SQLAlchemy warnings
            # Delete in proper order to respect foreign key constraints

            from flask import current_app
            current_app.logger.debug(f'Starting deletion cascade for group {self.name} (ID: {self.id})')

            # 1. Delete email logs first (they reference participants and groups)
            email_deleted = EmailLog.query.filter_by(group_id=self.id).delete(synchronize_session=False)
            current_app.logger.debug(f'Deleted {email_deleted} email logs')

            # 2. Delete audit logs (they reference expenses and participants)
            audit_deleted = AuditLog.query.filter_by(group_id=self.id).delete(synchronize_session=False)
            current_app.logger.debug(f'Deleted {audit_deleted} audit logs')

            # 3. Delete settlement payments (they reference participants and settlement periods)
            payments_deleted = 0
            if period_ids:
                payments_deleted = SettlementPayment.query.filter(
                    SettlementPayment.settlement_period_id.in_(period_ids)
                ).delete(synchronize_session=False)
                db.session.flush()  # Flush to ensure payments are deleted before participants
            current_app.logger.debug(f'Deleted {payments_deleted} settlement payments')

            # 4. Delete expense shares (they reference both expenses and participants)
            from app.models import ExpenseShare
            expense_ids = [expense.id for expense in self.expenses]
            shares_deleted = 0
            if expense_ids:
                shares_deleted = ExpenseShare.query.filter(ExpenseShare.expense_id.in_(expense_ids)).delete(synchronize_session=False)
            current_app.logger.debug(f'Deleted {shares_deleted} expense shares')

            # 5. Delete expenses (they reference participants via paid_by_id)
            expenses_deleted = Expense.query.filter_by(group_id=self.id).delete(synchronize_session=False)
            current_app.logger.debug(f'Deleted {expenses_deleted} expenses')

            # 6. Delete participants
            participants_deleted = Participant.query.filter_by(group_id=self.id).delete(synchronize_session=False)
            current_app.logger.debug(f'Deleted {participants_deleted} participants')

            # 7. Delete settlement periods
            periods_deleted = SettlementPeriod.query.filter_by(group_id=self.id).delete(synchronize_session=False)
            current_app.logger.debug(f'Deleted {periods_deleted} settlement periods')

            # Expire the group's settlement_periods relationship to prevent StaleDataError
            # After bulk delete, SQLAlchemy's session still thinks the relationship exists
            # Expiring it prevents UPDATE attempts on already-deleted rows during commit
            db.session.expire(self, ['settlement_periods'])
            current_app.logger.debug('Expired settlement_periods relationship on group object')

            # 8. Finally delete the group itself
            current_app.logger.debug(f'Deleting group object {self.name}')
            db.session.delete(self)

            # Commit all deletions
            current_app.logger.debug('Committing all deletions to database')
            db.session.commit()
            current_app.logger.info(f'Successfully committed deletion of group {deleted_summary["group_name"]}')

        except Exception as e:
            # Rollback on any error
            current_app.logger.error(f'Error during group deletion for {deleted_summary["group_name"]}: {str(e)}', exc_info=True)
            db.session.rollback()
            raise e

        return deleted_summary


class Participant(db.Model):
    """Group participant model."""
    __tablename__ = 'participants'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120))
    color = db.Column(db.String(7), default='#3B82F6')  # Default blue color
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    joined_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    access_token = db.Column(db.String(40), unique=True, nullable=False, default=lambda: generate_token(32), index=True)
    last_accessed = db.Column(db.DateTime, nullable=True)
    
    # Foreign keys
    group_id = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=False, index=True)
    
    # Relationships
    group = db.relationship('Group', back_populates='participants')
    paid_expenses = db.relationship('Expense', back_populates='paid_by', cascade='all, delete-orphan')
    expense_shares = db.relationship('ExpenseShare', back_populates='participant', cascade='all, delete-orphan')
    
    def __init__(self, name: str, group_id: int, email: Optional[str] = None,
                 color: str = '#3B82F6', is_admin: bool = False, **kwargs):
        """Initialize Participant instance."""
        super().__init__(**kwargs)
        self.name = name
        self.group_id = group_id
        self.email = email
        self.color = color
        self.is_admin = is_admin
    
    def generate_access_url(self, base_url: str) -> str:
        """Generate personalized access URL for this participant."""
        return f"{base_url}/p/{self.access_token}"
    
    def update_last_accessed(self):
        """Update the last accessed timestamp."""
        from flask import current_app
        self.last_accessed = datetime.now(timezone.utc)
        try:
            db.session.commit()
        except Exception as e:
            current_app.logger.warning(f"Failed to update last_accessed for participant {self.id}: {e}")
            db.session.rollback()

    def can_exit_group(self) -> tuple[bool, str]:
        """
        Check if participant can exit the group.

        Returns:
            tuple: (can_exit: bool, reason: str)
        """
        from decimal import Decimal

        # Check if group is settled (can exit settled groups)
        if self.group.is_settled:
            return True, "OK"

        # Check if this is the last participant
        if len(self.group.participants) <= 1:
            return False, "Cannot exit - you are the last participant in the group"

        # Check if this is the only admin
        if self.is_admin:
            other_admins = [p for p in self.group.participants if p.is_admin and p.id != self.id]
            if not other_admins:
                return False, "Cannot exit - you are the only admin. Please promote another participant to admin first"

        # Check for unresolved balances
        balances = self.group.get_balances()
        participant_balance = float(balances.get(self.id, Decimal('0.0')))

        if abs(participant_balance) > 0.01:  # Has outstanding balance
            from app.utils import format_currency
            return False, f"Cannot exit - you have an outstanding balance of {format_currency(participant_balance, self.group.currency)}. Please settle your balance first"

        return True, "OK"

    def __repr__(self) -> str:
        return f'<Participant {self.name}>'


class Expense(db.Model):
    """Expense model."""
    __tablename__ = 'expenses'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    amount = db.Column(db.Numeric(15, 2), nullable=False)  # Increased precision for larger amounts
    category = db.Column(db.String(50), default='general')
    date = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    split_type = db.Column(db.String(20), default='EQUAL', nullable=False)  # Currently only EQUAL supported
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    
    # Currency support
    currency = db.Column(db.String(3), default=get_default_currency, nullable=False)          # Original currency
    original_amount = db.Column(db.Numeric(15, 2), nullable=False)             # Original amount
    exchange_rate = db.Column(db.Numeric(10, 6), default=1.0, nullable=False)  # Rate used for conversion
    
    # Settlement period tracking
    settlement_period = db.Column(db.String(20))  # e.g., '2024-09', '2024-10'
    is_archived = db.Column(db.Boolean, default=False, nullable=False)  # Archived during settlement
    
    # Foreign keys
    group_id = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=False, index=True)
    paid_by_id = db.Column(db.Integer, db.ForeignKey('participants.id'), nullable=False, index=True)
    
    # Relationships
    group = db.relationship('Group', back_populates='expenses')
    paid_by = db.relationship('Participant', back_populates='paid_expenses')
    expense_shares = db.relationship('ExpenseShare', back_populates='expense', cascade='all, delete-orphan')
    
    def __init__(self, title: str, amount: float, group_id: int, paid_by_id: int,
                 description: Optional[str] = None, category: str = 'general',
                 currency: str = 'USD', original_amount: Optional[float] = None,
                 exchange_rate: float = 1.0, split_type: str = 'EQUAL',
                 settlement_period: Optional[str] = None, is_archived: bool = False, **kwargs):
        """Initialize Expense instance."""
        super().__init__(**kwargs)
        self.title = title
        self.amount = amount
        self.group_id = group_id
        self.paid_by_id = paid_by_id
        self.description = description
        self.category = category
        self.currency = currency
        self.original_amount = original_amount or amount
        self.exchange_rate = exchange_rate
        self.split_type = split_type
        self.settlement_period = settlement_period
        self.is_archived = is_archived
    
    def __repr__(self) -> str:
        return f'<Expense {self.title}: ${self.amount}>'


class ExpenseShare(db.Model):
    """Individual expense share model."""
    __tablename__ = 'expense_shares'
    
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    
    # Foreign keys
    expense_id = db.Column(db.Integer, db.ForeignKey('expenses.id'), nullable=False, index=True)
    participant_id = db.Column(db.Integer, db.ForeignKey('participants.id'), nullable=False, index=True)
    
    # Relationships
    expense = db.relationship('Expense', back_populates='expense_shares')
    participant = db.relationship('Participant', back_populates='expense_shares')
    
    def __init__(self, amount: float, expense_id: int, participant_id: int, **kwargs):
        """Initialize ExpenseShare instance."""
        super().__init__(**kwargs)
        self.amount = amount
        self.expense_id = expense_id
        self.participant_id = participant_id
    
    def __repr__(self) -> str:
        return f'<ExpenseShare participant_id={self.participant_id}: ${self.amount}>'


class SettlementPeriod(db.Model):
    """Settlement period tracking for recurring groups."""
    __tablename__ = 'settlement_periods'

    id = db.Column(db.Integer, primary_key=True)
    period_name = db.Column(db.String(20), nullable=False)  # e.g., '2024-09'
    settled_at = db.Column(db.DateTime, nullable=False, index=True)
    total_amount = db.Column(db.Numeric(15, 2))  # Total expenses for this period
    participant_count = db.Column(db.Integer)  # Number of participants at settlement

    # Foreign key
    group_id = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=False, index=True)

    # Relationships
    group = db.relationship('Group', backref='settlement_periods')
    payments = db.relationship('SettlementPayment', back_populates='settlement_period', cascade='all, delete-orphan')

    def __init__(self, period_name: str, group_id: int, settled_at: Optional[datetime] = None,
                 total_amount: Optional[float] = None, participant_count: Optional[int] = None, **kwargs):
        """Initialize SettlementPeriod instance."""
        super().__init__(**kwargs)
        self.period_name = period_name
        self.group_id = group_id
        self.settled_at = settled_at or datetime.now(timezone.utc)
        self.total_amount = total_amount
        self.participant_count = participant_count

    def __repr__(self) -> str:
        return f'<SettlementPeriod {self.period_name}: ${self.total_amount}>'


class SettlementPayment(db.Model):
    """Payment tracking for settlements - who owes whom and payment confirmation status."""
    __tablename__ = 'settlement_payments'

    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Numeric(15, 2), nullable=False)  # Payment amount
    currency = db.Column(db.String(3), nullable=False)  # Payment currency
    is_paid = db.Column(db.Boolean, default=False, nullable=False, index=True)  # Payment confirmation status
    paid_at = db.Column(db.DateTime)  # When payment was confirmed
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    # Foreign keys
    settlement_period_id = db.Column(db.Integer, db.ForeignKey('settlement_periods.id'), nullable=False, index=True)
    from_participant_id = db.Column(db.Integer, db.ForeignKey('participants.id'), nullable=False, index=True)  # Debtor
    to_participant_id = db.Column(db.Integer, db.ForeignKey('participants.id'), nullable=False, index=True)  # Creditor
    paid_by_participant_id = db.Column(db.Integer, db.ForeignKey('participants.id'))  # Who confirmed payment

    # Relationships
    settlement_period = db.relationship('SettlementPeriod', back_populates='payments')
    from_participant = db.relationship('Participant', foreign_keys=[from_participant_id], backref='debts')
    to_participant = db.relationship('Participant', foreign_keys=[to_participant_id], backref='credits')
    paid_by_participant = db.relationship('Participant', foreign_keys=[paid_by_participant_id])

    def __init__(self, settlement_period_id: int, from_participant_id: int, to_participant_id: int,
                 amount: float, currency: str = 'USD', is_paid: bool = False, **kwargs):
        """Initialize SettlementPayment instance."""
        super().__init__(**kwargs)
        self.settlement_period_id = settlement_period_id
        self.from_participant_id = from_participant_id
        self.to_participant_id = to_participant_id
        self.amount = amount
        self.currency = currency
        self.is_paid = is_paid

    def mark_as_paid(self, confirmed_by_participant_id: int) -> None:
        """Mark payment as confirmed."""
        self.is_paid = True
        self.paid_at = datetime.now(timezone.utc)
        self.paid_by_participant_id = confirmed_by_participant_id

    def mark_as_unpaid(self) -> None:
        """Mark payment as unconfirmed (admin override)."""
        self.is_paid = False
        self.paid_at = None
        self.paid_by_participant_id = None

    def __repr__(self) -> str:
        status = "PAID" if self.is_paid else "UNPAID"
        return f'<SettlementPayment {self.from_participant_id}→{self.to_participant_id}: ${self.amount} {status}>'


class KnownEmail(db.Model):
    """Known email addresses for autocomplete."""
    __tablename__ = 'known_emails'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100))
    usage_count = db.Column(db.Integer, default=1, nullable=False, index=True)
    last_used = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    
    def __init__(self, email: str, name: Optional[str] = None, usage_count: int = 1, **kwargs):
        """Initialize KnownEmail instance."""
        super().__init__(**kwargs)
        self.email = email
        self.name = name
        self.usage_count = usage_count
    
    def __repr__(self) -> str:
        return f'<KnownEmail {self.email}>'


class ExchangeRate(db.Model):
    """Exchange rate cache for currency conversions."""
    __tablename__ = 'exchange_rates'
    
    id = db.Column(db.Integer, primary_key=True)
    from_currency = db.Column(db.String(3), nullable=False, index=True)
    to_currency = db.Column(db.String(3), nullable=False, index=True)
    rate = db.Column(db.Numeric(12, 6), nullable=False)  # Exchange rate with high precision
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    
    # Composite unique constraint
    __table_args__ = (db.UniqueConstraint('from_currency', 'to_currency', name='unique_currency_pair'),)
    
    def __repr__(self) -> str:
        return f'<ExchangeRate {self.from_currency}/{self.to_currency}: {self.rate}>'
    
    @property
    def is_stale(self) -> bool:
        """Check if exchange rate is older than 1 hour."""
        return (datetime.now(timezone.utc) - self.updated_at.replace(tzinfo=timezone.utc)).total_seconds() > 3600


class AuditLog(db.Model):
    """Audit log for tracking changes in groups."""
    __tablename__ = 'audit_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(50), nullable=False, index=True)  # 'expense_added', 'expense_deleted', 'participant_removed', etc.
    description = db.Column(db.Text, nullable=False)  # Human-readable description
    details = db.Column(db.JSON)  # Additional structured data
    performed_by = db.Column(db.String(100))  # Name of user who performed action
    performed_by_participant_id = db.Column(db.Integer, db.ForeignKey('participants.id', ondelete='SET NULL'), index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    
    # Foreign keys
    group_id = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=False, index=True)
    expense_id = db.Column(db.Integer, db.ForeignKey('expenses.id'), nullable=True, index=True)  # For expense-related actions
    participant_id = db.Column(db.Integer, db.ForeignKey('participants.id'), nullable=True, index=True)  # For participant-related actions
    
    # Relationships
    group = db.relationship('Group', backref='audit_logs')
    expense = db.relationship('Expense', backref='audit_logs')
    participant = db.relationship('Participant', foreign_keys=[participant_id], backref='audit_logs')
    performed_by_participant = db.relationship('Participant', foreign_keys=[performed_by_participant_id])
    
    def __init__(self, group_id: int, action: str, description: str,
                 performed_by: Optional[str] = None, performed_by_participant_id: Optional[int] = None,
                 expense_id: Optional[int] = None, participant_id: Optional[int] = None,
                 details: Optional[dict] = None, **kwargs):
        """Initialize AuditLog instance."""
        super().__init__(**kwargs)
        self.group_id = group_id
        self.action = action
        self.description = description
        self.performed_by = performed_by
        self.performed_by_participant_id = performed_by_participant_id
        self.expense_id = expense_id
        self.participant_id = participant_id
        self.details = details or {}
    
    def __repr__(self) -> str:
        return f'<AuditLog {self.action}: {self.description[:50]}>'


class EmailLog(db.Model):
    """Email tracking for rate limiting and audit purposes."""
    __tablename__ = 'email_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    email_address = db.Column(db.String(120), nullable=False, index=True)  # Recipient email
    email_type = db.Column(db.String(50), nullable=False, index=True)  # 'invitation', 'settlement', 'reminder', 'group_created'
    success = db.Column(db.Boolean, nullable=False, index=True)  # Whether email was sent successfully
    sent_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    
    # Optional foreign keys for tracking context
    group_id = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=True, index=True)
    participant_id = db.Column(db.Integer, db.ForeignKey('participants.id'), nullable=True, index=True)
    
    # Rate limiting fields
    sender_ip = db.Column(db.String(45))  # For IP-based rate limiting (supports IPv6)
    user_agent = db.Column(db.Text)  # For additional abuse detection
    
    # Relationships
    group = db.relationship('Group', backref='email_logs')
    participant = db.relationship('Participant', backref='email_logs')
    
    def __init__(self, email_address: str, email_type: str, success: bool, 
                 group_id: Optional[int] = None, participant_id: Optional[int] = None,
                 sender_ip: Optional[str] = None, user_agent: Optional[str] = None, **kwargs):
        """Initialize EmailLog instance."""
        super().__init__(**kwargs)
        self.email_address = email_address
        self.email_type = email_type
        self.success = success
        self.group_id = group_id
        self.participant_id = participant_id
        self.sender_ip = sender_ip
        self.user_agent = user_agent
    
    def __repr__(self) -> str:
        return f'<EmailLog {self.email_type} to {self.email_address}: {self.success}>'
    
    @classmethod
    def get_email_count(cls, email_address: Optional[str] = None, group_id: Optional[int] = None, 
                       hours: int = 24, email_type: Optional[str] = None) -> int:
        """Get count of successful emails sent within parameters."""
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
        query = cls.query.filter(
            cls.sent_at >= cutoff_time,
            cls.success.is_(True)
        )
        
        if email_address:
            query = query.filter(cls.email_address == email_address)
        if group_id:
            query = query.filter(cls.group_id == group_id)
        if email_type:
            query = query.filter(cls.email_type == email_type)
            
        return query.count()
    
    @classmethod
    def can_send_email(cls, email_address: str, email_type: str, group_id: Optional[int] = None) -> tuple[bool, str]:
        """
        Check if an email can be sent based on per-group rate limiting rules.
        
        Rate limiting is now PER-GROUP to prevent abuse within groups while allowing
        normal usage across different groups. For emails without group context,
        global limits are applied.
        
        Rate limiting can be disabled via EMAIL_RATE_LIMITING_ENABLED environment variable.
        Thresholds are configurable via environment variables.
        
        Args:
            email_address: Recipient email address
            email_type: Type of email ('invitation', 'settlement', 'reminder', etc.)
            group_id: Group ID for group-specific rate limiting (None for global emails)
        
        Returns:
            tuple: (can_send: bool, reason: str)
        """
        from flask import current_app
        
        # Check if rate limiting is enabled
        if not current_app.config.get('EMAIL_RATE_LIMITING_ENABLED', True):
            return True, "Rate limiting disabled"
        
        # Get configurable rate limits per email type (per 24 hours per group)
        rate_limits = {
            'reminder': current_app.config.get('EMAIL_LIMIT_REMINDER', 1),
            'settlement': current_app.config.get('EMAIL_LIMIT_SETTLEMENT', 5),
            'invitation': current_app.config.get('EMAIL_LIMIT_INVITATION', 25),
            'group_created': current_app.config.get('EMAIL_LIMIT_GROUP_CREATED', 19)
        }
        
        # Check type-specific limits
        if email_type in rate_limits:
            type_count = cls.get_email_count(
                email_address=email_address, 
                group_id=group_id, 
                hours=24, 
                email_type=email_type
            )
            limit = rate_limits[email_type]
            if type_count >= limit:
                scope = "for this group" if group_id else "globally"
                return False, f"Daily {email_type} email limit exceeded {scope} ({type_count}/{limit})"
        
        # Check total daily limit
        total_limit = current_app.config.get('EMAIL_LIMIT_TOTAL_DAILY', 50)
        total_count = cls.get_email_count(
            email_address=email_address, 
            group_id=group_id, 
            hours=24
        )
        if total_count >= total_limit:
            scope = "for this group" if group_id else "globally"
            return False, f"Daily email limit exceeded {scope} ({total_count}/{total_limit})"
        
        return True, "OK"