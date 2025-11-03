"""Background scheduler for automatic monthly settlements."""

import logging
from datetime import datetime, timezone, date

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.executors.pool import ThreadPoolExecutor

from app.models import Group, SettlementPeriod, db
from app.utils import send_final_settlement_report, calculate_settlements


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler = None


def create_scheduler(settlement_time='23:30', reminder_time='09:00'):
    """Create and configure the background scheduler."""
    global scheduler

    if scheduler is None:
        # Configure executors for gevent compatibility
        # Using ThreadPoolExecutor works with gevent's monkey patching
        executors = {
            'default': ThreadPoolExecutor(max_workers=1)
        }

        # Use system timezone (configured via TZ environment variable)
        scheduler = BackgroundScheduler(
            executors=executors,
            job_defaults={
                'coalesce': False,
                'max_instances': 1,
                'misfire_grace_time': 30
            }
        )
        
        # Parse settlement time (format: "HH:MM")
        settlement_hour, settlement_minute = map(int, settlement_time.split(':'))
        
        # Parse reminder time (format: "HH:MM")
        reminder_hour, reminder_minute = map(int, reminder_time.split(':'))
        
        # Add the daily settlement check job (uses system timezone)
        scheduler.add_job(
            func=check_and_process_settlements,
            trigger=CronTrigger(hour=settlement_hour, minute=settlement_minute),
            id='daily_settlement_check',
            name='Daily Settlement Check',
            replace_existing=True
        )
        
        # Add the daily reminder check job (uses system timezone)
        scheduler.add_job(
            func=check_and_send_settlement_reminders,
            trigger=CronTrigger(hour=reminder_hour, minute=reminder_minute),
            id='daily_reminder_check',
            name='Daily Settlement Reminder Check',
            replace_existing=True
        )
        
        # Get timezone info for logging
        import os
        import time
        tz_name = os.environ.get('TZ', time.tzname[0] if not time.daylight else time.tzname[1])
        logger.info(f"Background scheduler created with system timezone {tz_name}, settlement at {settlement_time}, reminders at {reminder_time}")
    
    return scheduler


def start_scheduler(settlement_time='23:30', reminder_time='09:00'):
    """Start the background scheduler."""
    global scheduler
    
    if scheduler is None:
        scheduler = create_scheduler(settlement_time, reminder_time)
    
    if not scheduler.running:
        scheduler.start()
        logger.info("Background scheduler started")
    else:
        logger.info("Background scheduler already running")


def stop_scheduler():
    """Stop the background scheduler."""
    global scheduler
    
    if scheduler and scheduler.running:
        scheduler.shutdown()
        logger.info("Background scheduler stopped")


def check_and_process_settlements():
    """Check for groups with due settlements and expired groups, then process them."""
    logger.info("=" * 60)
    logger.info("SETTLEMENT CHECK STARTED")
    logger.info("=" * 60)

    try:
        # Import here to avoid circular imports
        from app import create_app

        # Create application context for database operations
        app, _ = create_app()  # Unpack tuple (app, socketio)
        with app.app_context():
            today = datetime.now(timezone.utc)
            logger.info(f"Current UTC time: {today.isoformat()}")

            # Find all expired groups first (they take priority over recurring settlements)
            logger.info("Searching for expired groups...")
            expired_groups = Group.query.filter(
                Group.is_active.is_(True),
                Group.expires_at != None,
                Group.expires_at <= today
            ).all()

            logger.info(f"Found {len(expired_groups)} expired groups")
            for group in expired_groups:
                logger.info(f"  - {group.name} (ID: {group.id}, expires_at: {group.expires_at.isoformat() if group.expires_at else 'None'})")

            # Get IDs of expired groups to exclude from recurring processing
            expired_group_ids = {group.id for group in expired_groups}

            # Find recurring groups with settlements due, excluding those that are expiring
            logger.info("Searching for recurring groups with due settlements...")
            due_groups_query = Group.query.filter(
                Group.is_recurring.is_(True),
                Group.is_active.is_(True),
                Group.next_settlement_date != None
            )

            if expired_group_ids:
                due_groups_query = due_groups_query.filter(~Group.id.in_(expired_group_ids))

            all_due_candidates = due_groups_query.all()

            # Filter by date comparison (handle timezone-aware and timezone-naive datetimes)
            due_groups = []
            for group in all_due_candidates:
                if group.next_settlement_date:
                    # Make both datetimes timezone-aware for comparison
                    settlement_date = group.next_settlement_date
                    if settlement_date.tzinfo is None:
                        settlement_date = settlement_date.replace(tzinfo=timezone.utc)

                    logger.info(f"Checking group '{group.name}' (ID: {group.id})")
                    logger.info(f"  - next_settlement_date: {settlement_date.isoformat()}")
                    logger.info(f"  - current time: {today.isoformat()}")
                    logger.info(f"  - is due: {settlement_date <= today}")

                    if settlement_date <= today:
                        due_groups.append(group)

            logger.info(f"Found {len(due_groups)} recurring groups with due settlements")
            for group in due_groups:
                logger.info(f"  - {group.name} (ID: {group.id}, next_settlement: {group.next_settlement_date.isoformat() if group.next_settlement_date else 'None'})")
            
            # Process expired groups FIRST (they take priority and close permanently)
            for group in expired_groups:
                try:
                    # Lock group for update to prevent race conditions
                    locked_group = Group.query.filter_by(id=group.id).with_for_update().first()
                    if locked_group and locked_group.is_active and locked_group.expires_at:
                        # Double-check conditions after acquiring lock
                        # Ensure timezone-aware comparison
                        expires_at = locked_group.expires_at
                        if expires_at.tzinfo is None:
                            expires_at = expires_at.replace(tzinfo=timezone.utc)

                        if expires_at <= today:
                            process_expiration_settlement(locked_group)
                            logger.info(f"Successfully processed expiration settlement for group: {locked_group.name}")
                        else:
                            logger.info(f"Group {locked_group.name} no longer meets expiration criteria, skipping")
                    else:
                        logger.info(f"Group {group.name} was modified by another process, skipping")
                except Exception as e:
                    logger.error(f"Error processing expiration settlement for group {group.name}: {e}")
                    # Continue processing other groups even if one fails
                    continue
            
            # Then process recurring settlements (for groups that haven't expired)
            for group in due_groups:
                try:
                    # Lock group for update to prevent race conditions
                    locked_group = Group.query.filter_by(id=group.id).with_for_update().first()
                    if locked_group and locked_group.is_recurring and locked_group.is_active:
                        # Double-check conditions after acquiring lock
                        if locked_group.next_settlement_date:
                            # Ensure timezone-aware comparison
                            settlement_date = locked_group.next_settlement_date
                            if settlement_date.tzinfo is None:
                                settlement_date = settlement_date.replace(tzinfo=timezone.utc)

                            if settlement_date <= today:
                                process_automatic_settlement(locked_group)
                                logger.info(f"Successfully processed recurring settlement for group: {locked_group.name}")
                            else:
                                logger.info(f"Group {locked_group.name} no longer meets settlement criteria, skipping")
                        else:
                            logger.info(f"Group {locked_group.name} has no next_settlement_date, skipping")
                    else:
                        logger.info(f"Group {group.name} was modified by another process, skipping")
                except Exception as e:
                    logger.error(f"Error processing recurring settlement for group {group.name}: {e}")
                    # Continue processing other groups even if one fails
                    continue
            
            # Commit all changes
            db.session.commit()
            logger.info("=" * 60)
            logger.info("SETTLEMENT CHECK COMPLETED SUCCESSFULLY")
            logger.info("=" * 60)

    except Exception as e:
        logger.error("=" * 60)
        logger.error(f"ERROR IN SETTLEMENT CHECK: {e}")
        logger.error("=" * 60)
        import traceback
        logger.error(traceback.format_exc())
        if 'db' in locals():
            db.session.rollback()


def check_and_send_settlement_reminders():
    """Check for groups needing 3-day settlement reminders and send them."""
    logger.info("Starting daily settlement reminder check")
    
    try:
        # Import here to avoid circular imports
        from app import create_app
        from app.utils import send_settlement_reminder
        from datetime import timedelta
        
        # Create application context for database operations
        app, _ = create_app()  # Unpack tuple (app, socketio)
        with app.app_context():
            today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            three_days_from_now = today + timedelta(days=3)
            tomorrow = today + timedelta(days=1)

            # Find all recurring groups with settlements due in exactly 3 days
            # (between tomorrow and 3 days from now, to avoid sending multiple reminders)
            reminder_groups = Group.query.filter(
                Group.is_recurring.is_(True),
                Group.is_active.is_(True),
                Group.next_settlement_date != None,
                Group.next_settlement_date >= three_days_from_now,
                Group.next_settlement_date < three_days_from_now + timedelta(days=1)
            ).all()
            
            logger.info(f"Found {len(reminder_groups)} groups needing 3-day settlement reminders")
            
            total_reminders_sent = 0
            total_reminders_skipped = 0
            
            for group in reminder_groups:
                try:
                    # Get group balances
                    balances = group.get_balances(group.currency)
                    settlement_date = group.next_settlement_date.strftime('%B %d, %Y')
                    
                    # Send reminders to all participants with email addresses
                    for participant in group.participants:
                        if participant.email:
                            participant_balance = balances.get(participant.id, 0.0)
                            
                            success = send_settlement_reminder(
                                to_email=participant.email,
                                participant_name=participant.name,
                                group_name=group.name,
                                group_id=group.id,
                                participant_id=participant.id,
                                settlement_date=settlement_date,
                                current_balance=participant_balance,
                                currency=group.currency,
                                share_token=group.share_token
                            )
                            
                            if success:
                                total_reminders_sent += 1
                                logger.info(f"Sent settlement reminder to {participant.email} for group: {group.name}")
                            else:
                                total_reminders_skipped += 1
                                logger.warning(f"Skipped settlement reminder to {participant.email} for group: {group.name} (rate limited or failed)")
                    
                except Exception as e:
                    logger.error(f"Error sending settlement reminders for group {group.name}: {e}")
                    # Continue processing other groups even if one fails
                    continue
            
            logger.info(f"Settlement reminder check completed. Sent: {total_reminders_sent}, Skipped: {total_reminders_skipped}")
            
    except Exception as e:
        logger.error(f"Error in daily settlement reminder check: {e}")


def process_automatic_settlement(group: Group):
    """Process automatic settlement for a single group."""
    logger.info("-" * 60)
    logger.info(f"PROCESSING AUTOMATIC SETTLEMENT: {group.name} (ID: {group.id})")
    logger.info("-" * 60)

    # Get current balances and settlements
    balances = group.get_balances(group.currency)
    settlements = calculate_settlements(balances)

    logger.info(f"Current balances: {balances}")
    logger.info(f"Calculated settlements: {settlements}")

    # Only process if there are actual expenses to settle
    active_expenses = [exp for exp in group.expenses if not exp.is_archived]
    logger.info(f"Active expenses count: {len(active_expenses)}")

    if not active_expenses:
        logger.info(f"No active expenses to settle for group: {group.name}, updating next settlement date")
        update_next_settlement_date(group)
        return
    
    # Archive expenses and create settlement period
    today = date.today()
    period_name = today.strftime('%Y-%m')
    
    # Calculate total expenses for this period
    total_amount = sum(expense.amount for expense in active_expenses)
    
    # Create settlement period record
    settlement_period = SettlementPeriod(
        group_id=group.id,
        period_name=period_name,
        settled_at=datetime.now(timezone.utc),
        total_amount=total_amount,
        participant_count=len(group.participants)
    )
    db.session.add(settlement_period)
    
    # Archive current expenses
    for expense in active_expenses:
        expense.settlement_period = period_name
        expense.is_archived = True
    
    # Send settlement reports to participants
    success_count = 0
    participants_list = list(group.participants)
    logger.info(f"Sending settlement reports to {len(participants_list)} participants")

    for participant in participants_list:
        if participant.email:
            logger.info(f"Attempting to send settlement report to {participant.name} ({participant.email})")
            try:
                success, message = send_final_settlement_report(
                    participant.email,
                    participant.name,
                    group.name,
                    balances,
                    settlements,
                    participants_list,
                    group.currency,
                    is_period_settlement=True,
                    group_id=group.id,
                    participant_id=participant.id,
                    share_token=group.share_token
                )
                if success:
                    success_count += 1
                    logger.info(f"✓ Successfully sent settlement report to {participant.email}")
                else:
                    logger.warning(f"✗ Failed to send settlement report to {participant.email}: {message}")
            except Exception as e:
                logger.error(f"✗ Exception sending settlement report to {participant.email}: {e}")
                import traceback
                logger.error(traceback.format_exc())
        else:
            logger.info(f"Skipping {participant.name} - no email address")
    
    # Update next settlement date
    update_next_settlement_date(group)
    
    # Create audit log entry for recurring settlement
    from app.models import AuditLog
    audit_log = AuditLog(
        group_id=group.id,
        action='group_settled_recurring',
        description=f'Recurring settlement completed: {len(active_expenses)} expenses archived to period {period_name}. {success_count} email reports sent.',
        details={
            'settlement_type': 'recurring_settlement',
            'period_name': period_name,
            'total_amount': float(total_amount),  # Convert Decimal to float for JSON
            'participant_count': len(group.participants),
            'email_reports_sent': success_count,
            'expenses_archived': len(active_expenses),
            'next_settlement_date': group.next_settlement_date.isoformat() if group.next_settlement_date else None
        },
        performed_by='System (Auto-Settlement)'
    )
    db.session.add(audit_log)
    
    participants_with_email_count = sum(1 for p in participants_list if p.email)
    logger.info(f"Automatic settlement completed for {group.name}. "
                f"Sent {success_count} email reports out of {participants_with_email_count} participants with emails.")


def process_expiration_settlement(group: Group):
    """Process final settlement for an expired group and close it."""
    logger.info("-" * 60)
    logger.info(f"PROCESSING EXPIRATION SETTLEMENT: {group.name} (ID: {group.id})")
    logger.info("-" * 60)
    logger.info(f"Group expires_at: {group.expires_at.isoformat() if group.expires_at else 'None'}")

    # Get current balances and settlements
    balances = group.get_balances(group.currency)
    settlements = calculate_settlements(balances)

    logger.info(f"Current balances: {balances}")
    logger.info(f"Calculated settlements: {settlements}")

    # Check if there are active expenses to settle
    active_expenses = [exp for exp in group.expenses if not exp.is_archived]
    logger.info(f"Active expenses count: {len(active_expenses)}")
    
    if active_expenses:
        # Archive expenses and create settlement period for groups with expenses
        today = date.today()
        period_name = f"Final Settlement - {today.strftime('%Y-%m-%d')}"
        
        # Calculate total expenses for this period
        total_amount = sum(expense.amount for expense in active_expenses)
        
        # Create settlement period record
        settlement_period = SettlementPeriod(
            group_id=group.id,
            period_name=period_name,
            settled_at=datetime.now(timezone.utc),
            total_amount=total_amount,
            participant_count=len(group.participants)
        )
        db.session.add(settlement_period)
        
        # Archive current expenses
        for expense in active_expenses:
            expense.settlement_period = period_name
            expense.is_archived = True
        
        # Send final settlement reports to participants
        success_count = 0
        participants_list = list(group.participants)
        logger.info(f"Sending expiration settlement reports to {len(participants_list)} participants")

        for participant in participants_list:
            if participant.email:
                logger.info(f"Attempting to send expiration report to {participant.name} ({participant.email})")
                try:
                    success, message = send_final_settlement_report(
                        participant.email,
                        participant.name,
                        group.name,
                        balances,
                        settlements,
                        participants_list,
                        group.currency,
                        is_period_settlement=False,  # This is a final settlement
                        is_expiration_settlement=True,
                        group_id=group.id,
                        participant_id=participant.id,
                        share_token=group.share_token
                    )
                    if success:
                        success_count += 1
                        logger.info(f"✓ Successfully sent expiration report to {participant.email}")
                    else:
                        logger.warning(f"✗ Failed to send expiration report to {participant.email}: {message}")
                except Exception as e:
                    logger.error(f"✗ Exception sending expiration report to {participant.email}: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
            else:
                logger.info(f"Skipping {participant.name} - no email address")
        
        participants_with_email_count = sum(1 for p in participants_list if p.email)
        logger.info(f"Sent {success_count} final settlement email reports out of {participants_with_email_count} participants with emails.")
        
        # Create audit log entry for expiration settlement with expenses
        from app.models import AuditLog
        audit_log = AuditLog(
            group_id=group.id,
            action='group_expired_settled',
            description=f'Group expired and settled: {len(active_expenses)} expenses archived to period {period_name}. {success_count} email reports sent.',
            details={
                'settlement_type': 'expiration_settlement',
                'period_name': period_name,
                'total_amount': float(total_amount),  # Convert Decimal to float for JSON
                'participant_count': len(group.participants),
                'email_reports_sent': success_count,
                'expenses_archived': len(active_expenses),
                'expiration_date': group.expires_at.isoformat() if group.expires_at else None
            },
            performed_by='System (Auto-Expiration)'
        )
        db.session.add(audit_log)
    else:
        logger.info(f"No active expenses to settle for expired group: {group.name}")
        
        # Create audit log entry for expiration without settlement (no expenses)
        from app.models import AuditLog
        audit_log = AuditLog(
            group_id=group.id,
            action='group_expired_no_settlement',
            description=f'Group expired with no active expenses to settle.',
            details={
                'settlement_type': 'expiration_no_settlement',
                'participant_count': len(group.participants),
                'expiration_date': group.expires_at.isoformat() if group.expires_at else None
            },
            performed_by='System (Auto-Expiration)'
        )
        db.session.add(audit_log)
    
    # Close the group regardless of whether there were expenses
    group.is_active = False
    
    # If it was a recurring group, stop the recurrence
    if group.is_recurring:
        group.is_recurring = False
        group.next_settlement_date = None
        logger.info(f"Stopped recurrence for expired group: {group.name}")
    
    logger.info(f"Expiration settlement completed and group closed: {group.name}")


def update_next_settlement_date(group: Group):
    """Update the next settlement date for a recurring group."""
    import calendar

    # Use current settlement date as reference, not today
    # This ensures we don't skip months when settlement runs early in the month
    if group.next_settlement_date:
        reference_date = group.next_settlement_date.date() if hasattr(group.next_settlement_date, 'date') else group.next_settlement_date
    else:
        reference_date = date.today()

    # Calculate next month's last day from the reference date
    if reference_date.month == 12:
        next_month_year = reference_date.year + 1
        next_month = 1
    else:
        next_month_year = reference_date.year
        next_month = reference_date.month + 1

    last_day_next = calendar.monthrange(next_month_year, next_month)[1]
    next_settlement = date(next_month_year, next_month, last_day_next)

    # Create timezone-aware datetime to avoid comparison errors
    group.next_settlement_date = datetime.combine(
        next_settlement,
        datetime.min.time().replace(hour=23, minute=59),
        tzinfo=timezone.utc
    )

    logger.info(f"Updated next settlement date for {group.name} to {next_settlement}")


def get_scheduler_status() -> dict:
    """Get the current status of the scheduler."""
    global scheduler
    
    if scheduler is None:
        return {"running": False, "jobs": []}
    
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            "func": job.func.__name__ if job.func else None
        })
    
    return {
        "running": scheduler.running,
        "jobs": jobs
    }


def trigger_manual_settlement_check():
    """Manually trigger the settlement check (for testing/debugging)."""
    logger.info("Manual settlement check triggered")
    check_and_process_settlements()