"""Who a staff member can see, and how far down the tree.

Rank decides reach: a Head Teacher sees the whole school, a Deputy sees the
whole tree beneath them, a section head sees their own line, and everyone else
sees only their direct reports.
"""

from .models import SupportStaff, Teacher

# Higher number = wider view
RANK_LEVEL = {
    "HEAD": 5,
    "DEPUTY": 4,
    "SENIOR": 3,
    "TEACHER": 2,
    "INTERN": 1,
}

SCOPE_WHOLE_SCHOOL = 4  # HEAD and DEPUTY
SCOPE_FULL_SUBTREE = 3  # SENIOR, and any non-teaching staff who supervise


def staff_profile(user):
    teacher = getattr(user, "teacher_profile", None)
    if teacher is not None:
        return "TEACHING", teacher
    support = getattr(user, "support_profile", None)
    if support is not None:
        return "NON_TEACHING", support
    return None, None


def rank_level(user):
    """0 for non-staff; 1–5 for staff, by rank or by whether they supervise."""
    kind, profile = staff_profile(user)
    if profile is None:
        return 5 if (user.is_superuser or user.role == "ADMIN") else 0
    if kind == "TEACHING":
        return RANK_LEVEL.get(profile.rank, 2)
    # Non-teaching: supervising someone makes you a section head.
    return 3 if direct_reports(user) else 1


def direct_reports(user, school=None):
    """User accounts that report straight to this person, within one school.

    `school` defaults to the supervisor's own, so a reporting line entered by
    mistake can never reach across the tenant border.
    """
    school = school if school is not None else user.school
    if school is None:
        return set()
    ids = set(
        Teacher.objects.filter(supervisor=user, school=school)
        .exclude(user=user)
        .values_list("user_id", flat=True)
    )
    ids |= set(
        SupportStaff.objects.filter(supervisor=user, school=school)
        .exclude(user=user)
        .exclude(user__isnull=True)
        .values_list("user_id", flat=True)
    )
    return ids


def visible_staff_ids(user):
    """Every staff account this person may look into, by rank.

    - Head / Deputy: the whole school
    - Section heads: their own reporting subtree
    - Everyone else: direct reports only

    Whatever the rank, the school border always holds: this never returns an
    account from another tenant. The one exception is a platform superuser with
    no school of their own, who is operating above the tenancy line.
    """
    level = rank_level(user)
    school = user.school

    if user.is_superuser and school is None:
        ids = set(Teacher.objects.values_list("user_id", flat=True)) | set(
            SupportStaff.objects.exclude(user__isnull=True).values_list("user_id", flat=True)
        )
        ids.discard(user.id)
        return ids

    if school is None:
        return set()

    if user.is_superuser or user.role == "ADMIN" or level >= SCOPE_WHOLE_SCHOOL:
        ids = set(
            Teacher.objects.filter(school=school).values_list("user_id", flat=True)
        ) | set(
            SupportStaff.objects.filter(school=school)
            .exclude(user__isnull=True)
            .values_list("user_id", flat=True)
        )
        ids.discard(user.id)
        return ids

    seen = direct_reports(user)
    if level >= SCOPE_FULL_SUBTREE:
        # Walk down the tree; the graph is tiny and depth is bounded in practice.
        from django.contrib.auth import get_user_model

        User = get_user_model()
        frontier = set(seen)
        while frontier:
            children = set()
            for u in User.objects.filter(id__in=frontier):
                children |= direct_reports(u, school=school)
            children -= seen
            children.discard(user.id)
            seen |= children
            frontier = children
    return seen


def scope_label(user):
    level = rank_level(user)
    if user.is_superuser or user.role == "ADMIN":
        return "Whole school"
    if level >= SCOPE_WHOLE_SCHOOL:
        return "Whole school"
    if level >= SCOPE_FULL_SUBTREE:
        return "My department (all levels below me)"
    return "My direct reports"


def category_of(user):
    """The grouping a staff member belongs to in a supervisor's team list."""
    kind, profile = staff_profile(user)
    if profile is None:
        return "Other"
    if kind == "TEACHING":
        return "Teaching staff"
    return profile.get_category_display()
