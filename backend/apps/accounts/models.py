from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "School Admin"
        TEACHER = "TEACHER", "Teacher"
        SUPPORT = "SUPPORT", "Support staff"
        PARENT = "PARENT", "Parent/Guardian"

    role = models.CharField(max_length=10, choices=Role.choices, default=Role.TEACHER)
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users",
    )
    phone = models.CharField(max_length=15, blank=True, help_text="MSISDN, e.g. 2547XXXXXXXX")
    # An admin-generated password is a shared secret: the admin typed it, read
    # it aloud, and probably wrote it on a note. It is a handover credential,
    # not the staff member's own, so the app makes them replace it before they
    # can do anything else.
    must_change_password = models.BooleanField(
        default=False,
        help_text="Set when an admin issues a password; cleared once the user picks their own",
    )
    password_changed_at = models.DateTimeField(null=True, blank=True)
