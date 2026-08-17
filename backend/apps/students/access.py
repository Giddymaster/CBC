"""Which learner a given user is allowed to look at.

Staff see every learner at their school; a parent sees only the children
whose guardian record is theirs. Report cards, profiles and any other
per-learner endpoint route through here, so a parent can never read another
family's child by guessing an id — the one hole a school-scoped filter alone
leaves open, because every family shares the same school.
"""

from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied

from .models import Learner


def visible_learner(user, learner_id):
    """The learner if this user may see them, else 404/403. School first, then
    guardianship for a parent."""
    learner = get_object_or_404(
        Learner.objects.filter(school=user.school).select_related("pathway", "school"),
        pk=learner_id,
    )
    if getattr(user, "role", None) == "PARENT":
        guardian = getattr(user, "guardian_profile", None)
        if guardian is None or not guardian.learners.filter(pk=learner.pk).exists():
            raise PermissionDenied("You can only view your own children.")
    return learner
