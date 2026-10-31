"""Authentication for the demo app.

DELIBERATELY BUGGY - used as a GemmaGraph Bug Hunter demo target. Do not deploy.
"""

import hashlib

# BUG (circular import): auth -> db -> auth.
from db import backup_database, find_user

SECRET_KEY = "super-secret-demo-key-123"  # BUG: hardcoded secret


def hash_password(password):
    # BUG: unsalted MD5 is not a password hash.
    return hashlib.md5(password.encode()).hexdigest()


def login(username, password):
    user = find_user(username)
    if user is None:
        return False
    return user[2] == hash_password(password)


def admin_backup(request_params):
    # Passes untrusted input straight into a shell command in db.backup_database.
    backup_database(request_params.get("dest", "/tmp/backup.db"))
    return {"status": "backup started"}
