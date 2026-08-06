"""Who is the platform operator, and the boundary around them.

The single most important rule in the control plane: a **school admin is not an
operator**. A school admin runs one school; the operator runs the business that
sells to schools. Conflating them would let one customer see and bill another.

The operator is a Django superuser. That is already how the rest of the system
treats platform-level actions (national curriculum documents, cross-school
audit). This module just gives it a name and a guard, so operator-only code
fails closed rather than leaning on scattered `is_superuser` checks.
"""

from rest_framework.exceptions import PermissionDenied


def is_operator(user):
    """The platform owner/maintainer — above all schools, belonging to none.

    A superuser *with* a school is a school admin who happens to hold the flag
    (the demo `admin` is one). Requiring no school keeps the two planes apart:
    the operator runs the business; a school admin runs one school.
    """
    return bool(
        getattr(user, "is_authenticated", False)
        and user.is_superuser
        and user.school_id is None
    )


def require_operator(user):
    if not is_operator(user):
        raise PermissionDenied("This is the platform operator area.")
