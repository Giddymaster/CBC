"""Test settings for the PostgreSQL leg of CI.

Same as settings_test — fast hashing, stubbed services — but keeps whatever
database the environment configures instead of forcing in-memory SQLite. That is
the whole point of the job: to run the suite against the engine production uses.
"""

from .settings_test import *  # noqa: F401,F403
from .settings import DATABASES  # noqa: F401  (env-configured; Postgres in CI)
