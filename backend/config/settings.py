import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# Defaults to FALSE: a deploy that forgets to set DEBUG must fail safe (no
# stack traces, no insecure SECRET_KEY), not run wide open. Local development
# sets DEBUG=true in its .env.
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-insecure-key")
if not DEBUG and SECRET_KEY == "dev-only-insecure-key":
    # Fail loudly at startup rather than serving a whole school's records with a
    # signing key that is published in this repository.
    raise ImproperlyConfigured(
        "SECRET_KEY must be set in the environment when DEBUG is false."
    )

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "rest_framework",
    "rest_framework.authtoken",
    "django_filters",
    "corsheaders",
    # CBC apps
    "apps.common",
    "apps.accounts",
    "apps.schools",
    "apps.students",
    "apps.teachers",
    "apps.assessments",
    "apps.attendance",
    "apps.timetable",
    "apps.communication",
    "apps.payments",
    "apps.interop",
    "apps.facilities",
    "apps.knowledge",
    "apps.promotions",
    "apps.platform",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Serves Django's own static files (admin, DRF browser) straight from the
    # app, so a production box needs no separate static host. In dev, runserver
    # still handles static and this passes through.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# SQLite in dev; set POSTGRES_DB to switch to PostgreSQL (production).
if os.getenv("POSTGRES_DB"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("POSTGRES_DB"),
            "USER": os.getenv("POSTGRES_USER", "cbc"),
            "PASSWORD": os.getenv("POSTGRES_PASSWORD", ""),
            "HOST": os.getenv("POSTGRES_HOST", "localhost"),
            "PORT": os.getenv("POSTGRES_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Nairobi"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
    },
}
if not DEBUG:
    # Hashed, compressed static filenames in production (long-cache safe).
    # Requires `collectstatic`, which the Docker image runs at build time.
    STORAGES["staticfiles"]["BACKEND"] = (
        "whitenoise.storage.CompressedManifestStaticFilesStorage"
    )

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    # Token first so an unauthenticated API call answers 401 (not 403) and the
    # frontend can tell "logged out" from "not allowed".
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
        # A handover password works for nothing but changing itself until it
        # has been changed — enforced server-side, not just in the browser.
        "apps.accounts.permissions.PasswordChangeEnforced",
        # A lapsed subscription makes a school read-only. Reads are never
        # blocked; see apps/platform/entitlement.py.
        "apps.platform.entitlement.SubscriptionEntitlement",
    ],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.StandardPagination",
    "PAGE_SIZE": 50,
    # Only scoped views throttle (the login door); everything else is
    # authenticated traffic from the school's own staff.
    "DEFAULT_THROTTLE_RATES": {
        "login": os.getenv("LOGIN_THROTTLE_RATE", "10/min"),
        # Requesting or confirming a code — kept low so nobody can text-bomb a
        # number or grind reset codes.
        "verify": os.getenv("VERIFY_THROTTLE_RATE", "8/min"),
    },
}

CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if origin.strip()
]

# Behind Cloudflare/an ALB in production: assume HTTPS terminates upstream.
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", "true").lower() == "true"
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"
    SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
    SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
    CSRF_TRUSTED_ORIGINS = [
        o for o in CORS_ALLOWED_ORIGINS if o.startswith("https://")
    ]

# A hard ceiling on request bodies, so an upload cannot exhaust the box before
# a field validator ever runs. Per-field limits live in apps/common/uploads.py.
DATA_UPLOAD_MAX_MEMORY_SIZE = 30 * 1024 * 1024   # 30 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 30 * 1024 * 1024

# Where the app is reached, for building verification links in emails.
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:5173").rstrip("/")

# Transactional email. Empty EMAIL_API_KEY => console/log stub, like the SMS
# and M-Pesa stubs, so the whole flow is testable with no account.
EMAIL_API_PROVIDER = os.getenv("EMAIL_API_PROVIDER", "resend")  # resend | sendgrid
EMAIL_API_KEY = os.getenv("EMAIL_API_KEY", "")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "ShuleNest <noreply@shulenest.com>")

# Verification codes and links.
OTP_TTL_MINUTES = int(os.getenv("OTP_TTL_MINUTES", "10"))
OTP_MAX_ATTEMPTS = int(os.getenv("OTP_MAX_ATTEMPTS", "5"))

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_TASK_ALWAYS_EAGER = DEBUG  # run tasks inline in dev (no Redis needed)

# Africa's Talking (SMS). Empty AT_API_KEY => console/log stub mode.
AT_USERNAME = os.getenv("AT_USERNAME", "")
AT_API_KEY = os.getenv("AT_API_KEY", "")
AT_SENDER_ID = os.getenv("AT_SENDER_ID", "")

# WhatsApp Business Cloud API (Meta). Empty token => the same stub mode.
# The school registers its own number with Meta; these are that number's
# credentials. WHATSAPP_TEMPLATE is the approved template used for
# school-initiated notices — Meta refuses free-form text to a parent who has
# not messaged the school in the last 24 hours.
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
WHATSAPP_TEMPLATE = os.getenv("WHATSAPP_TEMPLATE", "")
WHATSAPP_TEMPLATE_LANG = os.getenv("WHATSAPP_TEMPLATE_LANG", "en")

# M-Pesa Daraja. Empty consumer key => sandbox-stub mode (no network calls).
DARAJA_CONSUMER_KEY = os.getenv("DARAJA_CONSUMER_KEY", "")
DARAJA_CONSUMER_SECRET = os.getenv("DARAJA_CONSUMER_SECRET", "")
DARAJA_SHORTCODE = os.getenv("DARAJA_SHORTCODE", "174379")
DARAJA_PASSKEY = os.getenv("DARAJA_PASSKEY", "")
DARAJA_BASE_URL = os.getenv("DARAJA_BASE_URL", "https://sandbox.safaricom.co.ke")
DARAJA_CALLBACK_URL = os.getenv("DARAJA_CALLBACK_URL", "https://example.com/api/payments/stk-callback/")
# The unguessable segment in the callback URL Safaricom is told to call. Blank
# closes both webhooks — an unconfigured money endpoint must never credit.
DARAJA_WEBHOOK_SECRET = os.getenv("DARAJA_WEBHOOK_SECRET", "")
