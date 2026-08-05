"""Test settings: same app config, but fast.

Real password hashing dominates the runtime of an API test suite that creates a
user per fixture — MD5 here cuts the suite from minutes to seconds. In-memory
SQLite and a null cache keep the rest off disk.
"""

from .settings import *  # noqa: F401,F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

CELERY_TASK_ALWAYS_EAGER = True
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

MEDIA_ROOT = BASE_DIR / "test-media"  # noqa: F405

# Keep the AI scheme generator and Daraja in stub mode regardless of .env.
ANTHROPIC_API_KEY = ""
DARAJA_CONSUMER_KEY = ""
AT_API_KEY = ""
