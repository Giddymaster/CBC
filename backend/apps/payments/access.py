"""Who may see and who may touch the money.

Three circles, not one:

- **The cashier** — the office and the bursar. They receipt payments, set the
  fee note and raise invoices, because handling money is their post.
- **The viewer** — the cashier, plus the head teacher and deputy. A head
  teacher must be able to answer "how much is outstanding in Grade 7?" without
  being able to write a receipt.
- **Everybody else** — a class teacher has no business reading the school's
  fee register, and a parent has no business reading another family's. Parents
  see their own children's fees through the parent portal.
"""


def is_office(user):
    return bool(
        getattr(user, "is_authenticated", False)
        and (user.is_superuser or user.role == "ADMIN")
    )


def is_bursar(user):
    """Non-teaching staff posted to accounts."""
    from apps.teachers.models import SupportStaff

    profile = getattr(user, "support_profile", None)
    return profile is not None and profile.category == SupportStaff.Category.BURSAR


def is_school_leadership(user):
    """Head teacher or deputy — they run the school, so they read its books."""
    from apps.teachers.supervision import SCOPE_WHOLE_SCHOOL, rank_level

    if getattr(user, "teacher_profile", None) is None:
        return False
    return rank_level(user) >= SCOPE_WHOLE_SCHOOL


def can_handle_fees(user):
    """Receipt payments, set the fee note, raise invoices."""
    return is_office(user) or is_bursar(user)


def can_view_fees(user):
    """Read the register, export and print it."""
    return can_handle_fees(user) or is_school_leadership(user)
