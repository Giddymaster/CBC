from django.db import models

from apps.common.models import SchoolScopedModel, TimeStampedModel


class Pathway(TimeStampedModel):
    """Senior School pathway (CBC): STEM, Social Sciences, Arts & Sports Science."""

    class Code(models.TextChoices):
        STEM = "STEM", "STEM"
        SOCIAL = "SOCIAL", "Social Sciences"
        ARTS_SPORTS = "ARTS_SPORTS", "Arts & Sports Science"

    code = models.CharField(max_length=15, choices=Code.choices, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return self.get_code_display()


class Guardian(SchoolScopedModel):
    user = models.OneToOneField(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="guardian_profile",
        help_text="Portal login for this guardian (role PARENT)",
    )
    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=15, help_text="MSISDN, e.g. 2547XXXXXXXX — SMS and M-Pesa anchor")
    email = models.EmailField(blank=True)
    relationship = models.CharField(max_length=30, blank=True)

    class Meta:
        ordering = ["full_name", "id"]

    def __str__(self):
        return f"{self.full_name} ({self.phone})"


class Learner(SchoolScopedModel):
    class Gender(models.TextChoices):
        MALE = "M", "Male"
        FEMALE = "F", "Female"

    class Grade(models.IntegerChoices):
        PG = -2, "PG"
        PP1 = -1, "PP1"
        PP2 = 0, "PP2"
        G1, G2, G3 = 1, 2, 3
        G4, G5, G6 = 4, 5, 6
        G7, G8, G9 = 7, 8, 9
        G10, G11, G12 = 10, 11, 12

    upi = models.CharField(
        max_length=20, blank=True, help_text="NEMIS/KEMIS Unique Personal Identifier"
    )
    admission_number = models.CharField(max_length=20)
    first_name = models.CharField(max_length=50)
    middle_name = models.CharField(max_length=50, blank=True)
    last_name = models.CharField(max_length=50)
    date_of_birth = models.DateField()
    gender = models.CharField(max_length=1, choices=Gender.choices)
    grade = models.IntegerField(choices=Grade.choices)
    stream = models.CharField(max_length=20, blank=True)
    pathway = models.ForeignKey(
        Pathway,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Assigned at Grade 9 -> 10 transition",
    )
    guardians = models.ManyToManyField(Guardian, related_name="learners", blank=True)
    active = models.BooleanField(default=True)
    extra = models.JSONField(
        default=dict, blank=True, help_text="Values for admin-defined learner columns"
    )

    class Meta:
        ordering = ["grade", "stream", "admission_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "admission_number"], name="unique_admission_per_school"
            )
        ]

    @property
    def full_name(self):
        return " ".join(p for p in [self.first_name, self.middle_name, self.last_name] if p)

    def __str__(self):
        return f"{self.full_name} ({self.admission_number})"


class LearnerField(SchoolScopedModel):
    """An extra column the admin adds to the learner register.

    Values live in Learner.extra keyed by `key`, so a school can track things
    we didn't model (birth certificate no, medical notes, bus route) without a
    schema change.
    """

    label = models.CharField(max_length=50)
    key = models.SlugField(max_length=50)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["school", "key"], name="unique_learner_field_key")
        ]

    def __str__(self):
        return self.label


class ClassGroup(SchoolScopedModel):
    """A class (grade + stream) with its assigned class teacher."""

    grade = models.IntegerField(choices=Learner.Grade.choices)
    stream = models.CharField(max_length=20, blank=True)
    class_teacher = models.ForeignKey(
        "teachers.Teacher",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="class_groups",
    )

    class Meta:
        ordering = ["grade", "stream"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "grade", "stream"], name="unique_class_group"
            )
        ]

    def __str__(self):
        return f"{Learner.Grade(self.grade).label} {self.stream}".strip()
