"""Gevent monkey patch - must be imported first in all entry points."""

from gevent import monkey

# Monkey patch everything for async I/O compatibility
# Gevent has better Python 3.13 support and no RLock warnings
monkey.patch_all()
