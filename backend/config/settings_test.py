"""Test settings: same app config, but fast.

Real password hashing dominates the runtime of an API test suite that creates a
user per fixture — MD5 here cuts the suite from minutes to seconds. In-memory
SQLite and a null cache keep the rest off disk.
"""

from .settings import *

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# The login rate limit is real in production but would trip a suite that signs
# in dozens of times from one address. Raise it out of the way here; a dedicated
# test exercises the throttle with its own low override.
REST_FRAMEWORK = {**REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": {"login": "10000/min"}}

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

CELERY_TASK_ALWAYS_EAGER = True
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

MEDIA_ROOT = BASE_DIR / "test-media"

# Keep the AI scheme generator and Daraja in stub mode regardless of .env.
ANTHROPIC_API_KEY = ""
DARAJA_CONSUMER_KEY = ""
AT_API_KEY = ""
