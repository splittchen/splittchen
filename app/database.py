"""Database initialization and management utilities.

Handles database connection retry logic and table creation for PostgreSQL
and SQLite backends. Implements graceful retry mechanism for containerized
deployments where database may not be immediately available.
"""

import time
from flask import current_app
from app import db


def _migrate_to_timestamptz():
    """Migrate timestamp columns to timestamptz on PostgreSQL.
    
    Idempotent: only alters columns that are still 'timestamp without time zone'.
    Assumes existing naive timestamps are UTC (which is the application convention).
    """
    db_url = str(db.engine.url)
    if 'postgresql' not in db_url and 'postgres' not in db_url:
        return  # Only needed for PostgreSQL; SQLite has no distinction

    # All (table, column) pairs that use DateTime(timezone=True) in models.py
    columns_to_migrate = [
        ('groups', 'created_at'),
        ('groups', 'settled_at'),
        ('groups', 'expires_at'),
        ('groups', 'next_settlement_date'),
        ('participants', 'joined_at'),
        ('participants', 'last_accessed'),
        ('expenses', 'date'),
        ('expenses', 'created_at'),
        ('settlement_periods', 'settled_at'),
        ('settlement_payments', 'paid_at'),
        ('settlement_payments', 'created_at'),
        ('known_emails', 'last_used'),
        ('exchange_rates', 'updated_at'),
        ('audit_logs', 'created_at'),
        ('email_logs', 'sent_at'),
    ]

    migrated = 0
    for table, column in columns_to_migrate:
        try:
            # Check current column type via information_schema
            result = db.session.execute(db.text(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name = :table AND column_name = :col"
            ), {'table': table, 'col': column})
            row = result.fetchone()
            if row and row[0] == 'timestamp without time zone':
                db.session.execute(db.text(
                    f'ALTER TABLE "{table}" ALTER COLUMN "{column}" '
                    f'TYPE TIMESTAMPTZ USING "{column}" AT TIME ZONE \'UTC\''
                ))
                migrated += 1
                current_app.logger.info(f"Migrated {table}.{column} to TIMESTAMPTZ")
        except Exception as e:
            current_app.logger.warning(f"Could not migrate {table}.{column}: {e}")

    if migrated > 0:
        db.session.commit()
        current_app.logger.info(f"TIMESTAMPTZ migration complete: {migrated} column(s) converted")
    else:
        current_app.logger.info("TIMESTAMPTZ migration: all columns already up to date")


def init_database():
    """Initialize database tables if they don't exist.
    
    Implements retry logic for database connection (useful in Docker Compose
    where PostgreSQL may take time to become ready). Creates all SQLAlchemy
    models if tables don't exist, or connects to existing schema.
    
    Raises:
        Exception: If database connection fails after max_retries or if
                  table creation fails for reasons other than race conditions
    """
    max_retries = 30  # 30 seconds total
    retry_delay = 1   # 1 second between retries
    
    for attempt in range(max_retries):
        try:
            # Check if database tables exist by trying to query a core table
            from app.models import Group
            db.session.execute(db.text("SELECT 1 FROM groups LIMIT 1"))
            current_app.logger.info("Database tables already exist")
            _migrate_to_timestamptz()
            return
        except Exception as e:
            # Check if this is a connection error (database not ready yet)
            if "connection" in str(e).lower() or "refused" in str(e).lower():
                if attempt < max_retries - 1:
                    current_app.logger.info(f"Database not ready yet (attempt {attempt + 1}/{max_retries}), retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
                    continue
                else:
                    current_app.logger.error(f"Database connection failed after {max_retries} attempts: {e}")
                    raise
            
            # Tables don't exist, create them
            try:
                current_app.logger.info("Database tables not found, creating all tables...")
                db.create_all()
                current_app.logger.info("Database initialization completed successfully")
                return
            except Exception as create_error:
                # Check if this is a race condition where another process already created tables
                if "duplicate" in str(create_error).lower() or "already exists" in str(create_error).lower():
                    current_app.logger.info("Tables were created by another process, continuing...")
                    return
                current_app.logger.error(f"Failed to initialize database: {create_error}")
                raise