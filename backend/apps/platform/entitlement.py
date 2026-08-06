"""The access gate: a lapsed subscription makes a school read-only.

Wired in as a default DRF permission, so it covers every API write without each
view having to remember it.

Two principles hold it in check:

- **Reads are never blocked.** A school that has stopped paying keeps full sight
  of its own data — learners, marks, fees. Only *changes* are withheld. Nobody
  is ever locked away from their own records.
- **It fails open on doubt.** If a school somehow has no subscription row, or the
  check itself errors, writes are allowed. A bug here must never freeze a paying
  school mid-term; the worst case of failing open is that an unpaid school keeps
  working until you notice, which is a business problem, not an outage.
"""

from rest_framework.permissions import SAFE_METHODS, BasePermission

from .access import is_operator

# Writes a lapsed school must still be able to make. Rotating a password is a
# security action, not a feature, and the login endpoint is not under DRF perms.
EXEMPT_PATHS = ("/api/me/password/",)

LAPSED_MESSAGE = (
    "This school's subscription has lapsed, so the system is in read-only mode. "
    "Your data is safe and fully visible — settle the outstanding invoice to "
    "resume editing. Contact the school administrator."
)


class SubscriptionEntitlement(BasePermission):
    message = LAPSED_MESSAGE

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True

        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return True  # authentication is IsAuthenticated's job, not ours
        if is_operator(user):
            return True  # the operator is above the tenant gate
        if getattr(user, "school_id", None) is None:
            return True
        if request.path in EXEMPT_PATHS:
            return True

        try:
            subscription = getattr(user.school, "subscription", None)
            if subscription is None:
                return True  # fail open — a provisioned school always has one
            return subscription.can_write()
        except Exception:
            return True  # never let an entitlement bug freeze a real school
