from django.conf import settings
from django.db import models
from django.utils import timezone

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
    class Relationship(models.TextChoices):
        MOTHER = "MOTHER", "Mother"
        FATHER = "FATHER", "Father"
        GUARDIAN = "GUARDIAN", "Legal guardian"
        GRANDPARENT = "GRANDPARENT", "Grandparent"
        SIBLING = "SIBLING", "Sibling"
        OTHER = "OTHER", "Other"

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
    alt_phone = models.CharField(max_length=15, blank=True)
    email = models.EmailField(blank=True)
    relationship = models.CharField(max_length=30, blank=True)
    national_id = models.CharField(max_length=20, blank=True, help_text="ID / passport number")
    occupation = models.CharField(max_length=100, blank=True)
    address = models.CharField(max_length=200, blank=True)
    is_primary_contact = models.BooleanField(
        default=False, help_text="The first person the school calls"
    )

    class Meta:
        ordering = ["full_name", "id"]

    def __str__(self):
        return f"{self.full_name} ({self.phone})"


class AdmissionRight(SchoolScopedModel):
    """Permission for a staff member to admit new learners.

    Admitting a child creates a permanent record with medical and next-of-kin
    detail, so it stays an admin power by default. The admin can delegate it —
    typically to the head teacher, a deputy, or a class teacher handling the
    Grade 1 intake — without handing over the rest of the admin portal.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="admission_rights"
    )
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="admission_rights_granted",
    )
    note = models.CharField(
        max_length=200, blank=True, help_text="e.g. Grade 1 intake, January 2027"
    )
    # Which grades they may admit into. Empty means every grade — the common
    # case; a class teacher running one intake gets just their grade(s).
    grades = models.JSONField(default=list, blank=True)
    expires_on = models.DateField(
        null=True, blank=True, help_text="Leave blank for no expiry"
    )
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "user"], name="one_admission_right_per_staff"
            )
        ]

    def is_current(self, today=None):
        today = today or timezone.localdate()
        return self.active and (self.expires_on is None or self.expires_on >= today)

    def __str__(self):
        return f"Admission rights — {self.user.get_full_name() or self.user.username}"


def can_admit(user):
    """May this account admit a learner? Admins always; delegated staff while
    their grant is active and unexpired."""
    if user.is_superuser or getattr(user, "role", None) == "ADMIN":
        return True
    if user.school_id is None:
        return False
    right = AdmissionRight.objects.filter(school_id=user.school_id, user=user).first()
    return bool(right and right.is_current())


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

    class Status(models.TextChoices):
        ENROLLED = "ENROLLED", "Enrolled"
        TRANSFERRED = "TRANSFERRED", "Transferred out"
        GRADUATED = "GRADUATED", "Completed Grade 12"
        WITHDRAWN = "WITHDRAWN", "Withdrawn"

    # `active` stays the flag every register and report filters on; `status`
    # says *why* a learner left, which "deactivated" could never distinguish.
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.ENROLLED
    )
    exit_date = models.DateField(null=True, blank=True)
    exit_note = models.CharField(max_length=200, blank=True)
    active = models.BooleanField(default=True)
    extra = models.JSONField(
        default=dict, blank=True, help_text="Values for admin-defined learner columns"
    )

    # --- Admission record ------------------------------------------------
    # Everything the school is expected to hold on a child. Almost all of it
    # is optional: a parent arriving without a birth certificate should not be
    # a reason a child cannot be enrolled.
    photo = models.ImageField(upload_to="learner_photos/", null=True, blank=True)
    birth_certificate_no = models.CharField(max_length=30, blank=True)
    nationality = models.CharField(max_length=50, blank=True, default="Kenyan")
    religion = models.CharField(max_length=50, blank=True)
    admission_date = models.DateField(null=True, blank=True)
    admitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="learners_admitted",
        help_text="Staff member who completed the admission form",
    )

    # Where the child comes from
    previous_school = models.CharField(max_length=150, blank=True)
    previous_grade = models.CharField(max_length=30, blank=True)
    transfer_reason = models.CharField(max_length=200, blank=True)

    # Where the child lives
    county = models.CharField(max_length=50, blank=True)
    subcounty = models.CharField(max_length=50, blank=True)
    ward = models.CharField(max_length=50, blank=True)
    home_address = models.CharField(max_length=200, blank=True)

    class Residence(models.TextChoices):
        DAY = "DAY", "Day scholar"
        BOARDER = "BOARDER", "Boarder"

    residence = models.CharField(
        max_length=8, choices=Residence.choices, default=Residence.DAY
    )

    class Transport(models.TextChoices):
        WALKS = "WALK", "Walks"
        SCHOOL_BUS = "BUS", "School bus"
        PRIVATE = "PRIVATE", "Private/parent drop-off"
        PUBLIC = "PUBLIC", "Public transport"

    transport = models.CharField(
        max_length=8, choices=Transport.choices, blank=True
    )
    bus_route = models.CharField(max_length=100, blank=True)

    # Health — matters on the day something goes wrong
    class BloodGroup(models.TextChoices):
        A_POS = "A+", "A+"
        A_NEG = "A-", "A-"
        B_POS = "B+", "B+"
        B_NEG = "B-", "B-"
        AB_POS = "AB+", "AB+"
        AB_NEG = "AB-", "AB-"
        O_POS = "O+", "O+"
        O_NEG = "O-", "O-"

    blood_group = models.CharField(max_length=3, choices=BloodGroup.choices, blank=True)
    allergies = models.TextField(blank=True)
    chronic_conditions = models.TextField(
        blank=True, help_text="e.g. asthma, epilepsy, sickle cell"
    )
    medication = models.TextField(blank=True, help_text="Regular medication and dosage")
    nhif_number = models.CharField(max_length=30, blank=True)
    immunisation_up_to_date = models.BooleanField(null=True, blank=True)
    special_needs = models.TextField(
        blank=True, help_text="Learning support, mobility, vision, hearing"
    )

    # Who to call when the guardians cannot be reached
    emergency_contact_name = models.CharField(max_length=150, blank=True)
    emergency_contact_phone = models.CharField(max_length=15, blank=True)
    emergency_contact_relationship = models.CharField(max_length=50, blank=True)

    admission_notes = models.TextField(blank=True)

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
