"""Database initialization and management utilities.

Handles database connection retry logic and table creation for PostgreSQL
and SQLite backends. Implements graceful retry mechanism for containerized
deployments where database may not be immediately available.
"""

import time
from flask import current_app
from app import db


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