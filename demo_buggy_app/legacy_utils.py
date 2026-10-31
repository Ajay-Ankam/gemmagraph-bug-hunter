"""Legacy helpers left over from v1.

DELIBERATELY BUGGY - used as a GemmaGraph Bug Hunter demo target. Do not deploy.
"""

import pickle


def format_username(name):
    return name.strip().lower()


def load_legacy_session(blob):
    # DEAD CODE: nothing in the app calls this anymore.
    # It is also unsafe: pickle.loads on untrusted data allows code execution.
    return pickle.loads(blob)


def old_password_check(stored, given):
    # DEAD CODE: replaced by auth.login in v2.
    return stored == given
