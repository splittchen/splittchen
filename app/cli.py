"""CLI commands for the application."""

import click
from flask import current_app
from flask.cli import with_appcontext
from datetime import datetime, timezone, timedelta


@click.command()
@with_appcontext
def check_settlements():
    """Manually check and process due settlements."""
    from app.scheduler import trigger_manual_settlement_check
    click.echo("Checking for due settlements...")
    trigger_manual_settlement_check()
    click.echo("Settlement check completed.")


@click.command()
@with_appcontext
def scheduler_status():
    """Show scheduler status and jobs."""
    from app.scheduler import get_scheduler_status
    status = get_scheduler_status()
    click.echo(f"Scheduler running: {status['running']}")
    click.echo(f"Jobs: {len(status['jobs'])}")
    for job in status['jobs']:
        click.echo(f"  - {job['name']} (ID: {job['id']}) - Next run: {job['next_run']}")


@click.command()
@with_appcontext
def list_groups():
    """List all groups with settlement information."""
    from app.models import Group

    click.echo("=" * 80)
    click.echo("ALL GROUPS")
    click.echo("=" * 80)

    groups = Group.query.all()
    if not groups:
        click.echo("No groups found.")
        return

    now = datetime.now(timezone.utc)
    click.echo(f"Current UTC time: {now.isoformat()}")
    click.echo()

    for group in groups:
        # Determine overall status
        is_expired = False
        if group.expires_at:
            expires_at = group.expires_at.replace(tzinfo=timezone.utc) if group.expires_at.tzinfo is None else group.expires_at
            is_expired = expires_at <= now

        # Show status more clearly
        if is_expired:
            status = "EXPIRED"
        elif group.is_settled:
            status = "SETTLED"
        elif group.is_active:
            status = "ACTIVE"
        else:
            status = "CLOSED"

        click.echo(f"Group: {group.name} (ID: {group.id}) - {status}")
        click.echo(f"  Share Token: {group.share_token}")
        click.echo(f"  Active: {group.is_active}")
        click.echo(f"  Settled: {group.is_settled}")
        click.echo(f"  Recurring: {group.is_recurring}")

        if group.expires_at:
            expires_at = group.expires_at.replace(tzinfo=timezone.utc) if group.expires_at.tzinfo is None else group.expires_at
            click.echo(f"  Expires At: {expires_at.isoformat()} {'(EXPIRED)' if is_expired else '(future)'}")

        if group.next_settlement_date:
            settlement_date = group.next_settlement_date.replace(tzinfo=timezone.utc) if group.next_settlement_date.tzinfo is None else group.next_settlement_date
            is_due = settlement_date <= now
            click.echo(f"  Next Settlement: {settlement_date.isoformat()} {'(DUE NOW)' if is_due else '(pending)'}")

        # Count active expenses
        active_expenses = [exp for exp in group.expenses if not exp.is_archived]
        click.echo(f"  Active Expenses: {len(active_expenses)}")
        click.echo(f"  Participants: {len(group.participants)}")
        click.echo()


@click.command()
@click.option('--group-id', type=int, help='Specific group ID to test')
@click.option('--dry-run', is_flag=True, help='Preview what would happen without making changes')
@with_appcontext
def test_settlement(group_id, dry_run):
    """Test settlement logic for specific group or all due groups."""
    from app.models import Group, db
    from app.scheduler import process_automatic_settlement, process_expiration_settlement

    click.echo("=" * 80)
    click.echo("SETTLEMENT TEST" + (" (DRY RUN)" if dry_run else ""))
    click.echo("=" * 80)

    now = datetime.now(timezone.utc)
    click.echo(f"Current UTC time: {now.isoformat()}")
    click.echo()

    if group_id:
        # Test specific group
        group = Group.query.get(group_id)
        if not group:
            click.echo(f"Error: Group {group_id} not found")
            return

        groups_to_test = [group]
    else:
        # Test all due groups
        groups_to_test = []

        # Find expired groups
        expired_groups = Group.query.filter(
            Group.is_active.is_(True),
            Group.expires_at != None
        ).all()

        for g in expired_groups:
            expires_at = g.expires_at.replace(tzinfo=timezone.utc) if g.expires_at.tzinfo is None else g.expires_at
            if expires_at <= now:
                groups_to_test.append(('expired', g))

        # Find recurring groups
        recurring_groups = Group.query.filter(
            Group.is_recurring.is_(True),
            Group.is_active.is_(True),
            Group.next_settlement_date != None
        ).all()

        for g in recurring_groups:
            settlement_date = g.next_settlement_date.replace(tzinfo=timezone.utc) if g.next_settlement_date.tzinfo is None else g.next_settlement_date
            if settlement_date <= now:
                groups_to_test.append(('recurring', g))

    if not groups_to_test:
        click.echo("No groups due for settlement.")
        return

    for item in groups_to_test:
        if isinstance(item, tuple):
            settlement_type, group = item
        else:
            group = item
            # Determine type
            if group.expires_at:
                expires_at = group.expires_at.replace(tzinfo=timezone.utc) if group.expires_at.tzinfo is None else group.expires_at
                if expires_at <= now:
                    settlement_type = 'expired'
                else:
                    settlement_type = 'recurring'
            else:
                settlement_type = 'recurring'

        click.echo(f"Testing {settlement_type} settlement for: {group.name} (ID: {group.id})")
        click.echo(f"  Active: {group.is_active}")
        click.echo(f"  Recurring: {group.is_recurring}")

        active_expenses = [exp for exp in group.expenses if not exp.is_archived]
        click.echo(f"  Active expenses: {len(active_expenses)}")
        click.echo(f"  Participants: {len(group.participants)}")

        if dry_run:
            click.echo(f"  [DRY RUN] Would process {settlement_type} settlement")
        else:
            try:
                if settlement_type == 'expired':
                    process_expiration_settlement(group)
                else:
                    process_automatic_settlement(group)
                db.session.commit()
                click.echo(f"  ✓ Successfully processed {settlement_type} settlement")
            except Exception as e:
                db.session.rollback()
                click.echo(f"  ✗ Error processing settlement: {e}")
                import traceback
                click.echo(traceback.format_exc())

        click.echo()


@click.command()
@click.argument('share_token')
@click.option('--days', type=int, default=0, help='Days from now (use negative for past)')
@with_appcontext
def set_settlement_date(share_token, days):
    """Set next settlement date for a recurring group (for testing)."""
    from app.models import Group, db

    group = Group.query.filter_by(share_token=share_token).first()
    if not group:
        click.echo(f"Error: Group not found with share token: {share_token}")
        return

    if not group.is_recurring:
        click.echo(f"Error: Group '{group.name}' is not a recurring group")
        return

    target_date = datetime.now(timezone.utc) + timedelta(days=days)
    group.next_settlement_date = target_date

    try:
        db.session.commit()
        click.echo(f"✓ Updated next settlement date for '{group.name}' to: {target_date.isoformat()}")
        click.echo(f"  Current time: {datetime.now(timezone.utc).isoformat()}")
        if days <= 0:
            click.echo(f"  Settlement is now DUE - run 'flask check-settlements' to process")
    except Exception as e:
        db.session.rollback()
        click.echo(f"✗ Error: {e}")


@click.command()
@click.argument('share_token')
@click.option('--days', type=int, default=0, help='Days from now (use negative for past)')
@with_appcontext
def set_expiration_date(share_token, days):
    """Set expiration date for a group (for testing)."""
    from app.models import Group, db

    group = Group.query.filter_by(share_token=share_token).first()
    if not group:
        click.echo(f"Error: Group not found with share token: {share_token}")
        return

    target_date = datetime.now(timezone.utc) + timedelta(days=days)
    group.expires_at = target_date

    try:
        db.session.commit()
        click.echo(f"✓ Updated expiration date for '{group.name}' to: {target_date.isoformat()}")
        click.echo(f"  Current time: {datetime.now(timezone.utc).isoformat()}")
        if days <= 0:
            click.echo(f"  Group is now EXPIRED - run 'flask check-settlements' to process")
    except Exception as e:
        db.session.rollback()
        click.echo(f"✗ Error: {e}")


def register_cli_commands(app):
    """Register all CLI commands with the Flask app."""
    app.cli.add_command(check_settlements)
    app.cli.add_command(scheduler_status)
    app.cli.add_command(list_groups)
    app.cli.add_command(test_settlement)
    app.cli.add_command(set_settlement_date)
    app.cli.add_command(set_expiration_date)