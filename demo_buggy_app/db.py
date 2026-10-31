"""Database layer for the demo app.

DELIBERATELY BUGGY - used as a GemmaGraph Bug Hunter demo target. Do not deploy.
"""

import sqlite3
import subprocess

# BUG (circular import): db -> auth -> db. The data layer should never import auth.
from auth import hash_password

DB_PATH = "users.db"


def get_connection():
    return sqlite3.connect(DB_PATH)


def find_user(username):
    conn = get_connection()
    cursor = conn.cursor()
    # BUG (SQL injection): user input is formatted straight into the query.
    query = f"SELECT id, username, password_hash FROM users WHERE username = '{username}'"
    cursor.execute(query)
    row = cursor.fetchone()
    conn.close()
    return row


def create_user(username, password):
    conn = get_connection()
    conn.execute(
        "INSERT INTO users (username, password_hash) VALUES (?, ?)",
        (username, hash_password(password)),
    )
    conn.commit()
    conn.close()


def backup_database(destination):
    # BUG (command injection): destination comes from an HTTP request param.
    subprocess.run(f"cp {DB_PATH} {destination}", shell=True)
