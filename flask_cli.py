#!/usr/bin/env python3
"""Flask CLI wrapper that ensures gevent monkey patching happens first.

This file should be used as FLASK_APP entry point for CLI commands.
"""

# CRITICAL: Monkey patch MUST happen before ANY other imports
import gevent_patch  # noqa: F401

from app import create_app

# Create the app for Flask CLI
app, socketio = create_app()

# This makes the app available to Flask CLI
if __name__ == '__main__':
    # This allows running: python flask_cli.py
    # But normally you'd run: flask <command>
    pass
