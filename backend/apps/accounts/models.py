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
