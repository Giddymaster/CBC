"""Test settings for the PostgreSQL leg of CI.

Same as settings_test — fast hashing, stubbed services — but keeps whatever
database the environment configures instead of forcing in-memory SQLite. That is
the whole point of the job: to run the suite against the engine production uses.

The override is a plain assignment rather than a second import on purpose: an
import-order-dependent override is exactly the kind of thing an import sorter
silently reorders, and did — leaving this file importing SQLite last and the
"PostgreSQL job" testing nothing.
"""

from .settings import DATABASES as ENV_DATABASES
from .settings_test import *  # noqa: F403

DATABASES = ENV_DATABASES
