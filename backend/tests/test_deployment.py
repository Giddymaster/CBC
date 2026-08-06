"""The configuration nobody exercises locally.

Production settings only differ when DEBUG is off, which is exactly the state a
developer never runs in — so the differences are asserted here rather than
discovered on a live server.

`config/settings.py` is executed in a fresh namespace for each case rather than
reloaded. `importlib.reload` re-runs the module *into its existing namespace*,
so a name the new run does not reassign survives from the previous one — which
would quietly make a DEBUG=true case inherit the DEBUG=false security settings
and assert nothing.

The `check --deploy` run lives in CI, not here: `call_command` reads Django's
already-configured settings object, so it could only ever check the test
settings. CI runs it as a real process with the production environment.
"""

import os
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase

SETTINGS_FILE = Path(__file__).resolve().parent.parent / "config" / "settings.py"

REAL_KEY = "a-real-key-with-plenty-of-entropy-for-these-tests-0123456789"
PRODUCTION = {
    "DEBUG": "false",
    "SECRET_KEY": REAL_KEY,
    "ALLOWED_HOSTS": "example.test",
    "CORS_ALLOWED_ORIGINS": "https://example.test",
}
DEVELOPMENT = {"DEBUG": "true", "SECRET_KEY": "dev-only-insecure-key"}

# Names settings.py reads from the environment. Cleared between cases so one
# test's variables cannot leak into the next.
MANAGED = [
    "DEBUG", "SECRET_KEY", "ALLOWED_HOSTS", "CORS_ALLOWED_ORIGINS",
    "SECURE_SSL_REDIRECT", "SECURE_HSTS_SECONDS", "POSTGRES_DB",
]


def load(env):
    """Execute config/settings.py in a clean namespace under `env`."""
    cleared = {name: "" for name in MANAGED}
    with patch.dict(os.environ, {**cleared, **env}, clear=False):
        for name in MANAGED:
            if name not in env:
                os.environ.pop(name, None)
        namespace = {"__file__": str(SETTINGS_FILE), "__name__": "config.settings_probe"}
        exec(compile(SETTINGS_FILE.read_text(encoding="utf-8"), str(SETTINGS_FILE), "exec"),
             namespace)
        return namespace


class ProductionSettingsTests(SimpleTestCase):
    def test_it_refuses_to_start_without_a_real_secret_key(self):
        """Better to fail at startup than serve a school's records signed with
        a key published in this repository."""
        from django.core.exceptions import ImproperlyConfigured

        with self.assertRaises(ImproperlyConfigured):
            load({**PRODUCTION, "SECRET_KEY": "dev-only-insecure-key"})

    def test_the_dev_default_is_fine_while_debug_is_on(self):
        settings = load(DEVELOPMENT)
        self.assertTrue(settings["DEBUG"])
        self.assertEqual(settings["SECRET_KEY"], "dev-only-insecure-key")

    def test_production_turns_on_the_transport_protections(self):
        s = load(PRODUCTION)
        self.assertTrue(s["SESSION_COOKIE_SECURE"])
        self.assertTrue(s["CSRF_COOKIE_SECURE"])
        self.assertTrue(s["SECURE_HSTS_SECONDS"])
        self.assertTrue(s["SECURE_HSTS_INCLUDE_SUBDOMAINS"])
        self.assertTrue(s["SECURE_HSTS_PRELOAD"])
        self.assertTrue(s["SECURE_CONTENT_TYPE_NOSNIFF"])
        self.assertTrue(s["SECURE_SSL_REDIRECT"])
        self.assertEqual(s["X_FRAME_OPTIONS"], "DENY")
        self.assertEqual(
            s["SECURE_PROXY_SSL_HEADER"], ("HTTP_X_FORWARDED_PROTO", "https")
        )

    def test_dev_does_not_force_https_on_localhost(self):
        self.assertNotIn("SECURE_SSL_REDIRECT", load(DEVELOPMENT))

    def test_ssl_redirect_can_be_turned_off_behind_a_terminator(self):
        s = load({**PRODUCTION, "SECURE_SSL_REDIRECT": "false"})
        self.assertFalse(s["SECURE_SSL_REDIRECT"])

    def test_cors_origins_come_from_the_environment(self):
        s = load({**PRODUCTION, "CORS_ALLOWED_ORIGINS": "https://a.test, https://b.test"})
        self.assertEqual(s["CORS_ALLOWED_ORIGINS"], ["https://a.test", "https://b.test"])

    def test_only_https_origins_are_trusted_for_csrf(self):
        s = load({**PRODUCTION, "CORS_ALLOWED_ORIGINS": "https://a.test,http://b.test"})
        self.assertEqual(s["CSRF_TRUSTED_ORIGINS"], ["https://a.test"])

    def test_sqlite_is_the_default(self):
        self.assertEqual(
            load(DEVELOPMENT)["DATABASES"]["default"]["ENGINE"],
            "django.db.backends.sqlite3",
        )

    def test_postgres_is_selected_by_environment(self):
        s = load({**PRODUCTION, "POSTGRES_DB": "cbc"})
        self.assertEqual(
            s["DATABASES"]["default"]["ENGINE"], "django.db.backends.postgresql"
        )

    def test_celery_is_not_eager_in_production(self):
        """Eager tasks would run report-card generation inside the request that
        asked for it."""
        self.assertFalse(load(PRODUCTION)["CELERY_TASK_ALWAYS_EAGER"])
        self.assertTrue(load(DEVELOPMENT)["CELERY_TASK_ALWAYS_EAGER"])

    def test_external_services_stay_stubbed_until_configured(self):
        s = load(PRODUCTION)
        self.assertEqual(s["AT_API_KEY"], "")
        self.assertEqual(s["DARAJA_CONSUMER_KEY"], "")

    def test_token_auth_is_tried_before_session_auth(self):
        """So an unauthenticated API call answers 401, not 403, and the client
        can tell 'logged out' from 'not allowed'."""
        classes = load(PRODUCTION)["REST_FRAMEWORK"]["DEFAULT_AUTHENTICATION_CLASSES"]
        self.assertIn("TokenAuthentication", classes[0])

    def test_whitenoise_serves_static_in_production(self):
        """Django's own static (admin, DRF) is served by the app, so a box needs
        no separate static host."""
        s = load(PRODUCTION)
        # Middleware present, and right after SecurityMiddleware.
        mw = s["MIDDLEWARE"]
        self.assertIn("whitenoise.middleware.WhiteNoiseMiddleware", mw)
        self.assertEqual(mw.index("whitenoise.middleware.WhiteNoiseMiddleware"), 1)
        self.assertEqual(
            s["STORAGES"]["staticfiles"]["BACKEND"],
            "whitenoise.storage.CompressedManifestStaticFilesStorage",
        )

    def test_dev_uses_plain_static_storage(self):
        """The compressed-manifest backend needs collectstatic; runserver in dev
        would break with it, so dev keeps the plain backend."""
        s = load(DEVELOPMENT)
        self.assertEqual(
            s["STORAGES"]["staticfiles"]["BACKEND"],
            "django.contrib.staticfiles.storage.StaticFilesStorage",
        )

    def test_the_entitlement_gate_is_a_default_permission(self):
        """A lapsed school is read-only everywhere, not per-view."""
        perms = load(PRODUCTION)["REST_FRAMEWORK"]["DEFAULT_PERMISSION_CLASSES"]
        self.assertIn("apps.platform.entitlement.SubscriptionEntitlement", perms)
