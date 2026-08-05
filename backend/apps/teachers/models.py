from django.conf import settings
from django.db import models

from apps.common.models import SchoolScopedModel


class Teacher(SchoolScopedModel):
    class EmploymentType(models.TextChoices):
        TSC = "TSC", "Government (TSC)"
        PNP = "PNP", "PNP (Govt intern programme)"
        BOM = "BOM", "BOM employed"
        PTA = "PTA", "PTA employed"

    class Rank(models.TextChoices):
        HEAD = "HEAD", "Head Teacher"
        DEPUTY = "DEPUTY", "Deputy Head Teacher"
        SENIOR = "SENIOR", "Senior Teacher"
        TEACHER = "TEACHER", "Teacher"
        INTERN = "INTERN", "Intern Teacher"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="teacher_profile"
    )
    tsc_number = models.CharField(
        max_length=20, unique=True, help_text="TSC number, or a school payroll no for BOM/PTA"
    )
    employment_type = models.CharField(
        max_length=4, choices=EmploymentType.choices, default=EmploymentType.TSC
    )
    rank = models.CharField(max_length=10, choices=Rank.choices, default=Rank.TEACHER)
    learning_areas = models.ManyToManyField(
        "assessments.LearningArea", related_name="teachers", blank=True
    )
    extra = models.JSONField(
        default=dict, blank=True, help_text="Values for admin-defined staff columns"
    )
    supervisor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="supervises_teachers",
        help_text="Who this teacher reports to for submissions and approvals",
    )
    photo = models.ImageField(upload_to="staff_photos/", null=True, blank=True)

    class Meta:
        ordering = ["user__first_name", "user__last_name", "id"]

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} (TSC {self.tsc_number})"


class SupportStaff(SchoolScopedModel):
    """Non-teaching staff: kitchen, cleaners, security, bursar, secretary..."""

    class Category(models.TextChoices):
        BURSAR = "BURSAR", "Bursar / Accounts"
        SECRETARY = "SECRETARY", "Secretary / Admin"
        KITCHEN = "KITCHEN", "Kitchen staff"
        CLEANER = "CLEANER", "Cleaner"
        SECURITY = "SECURITY", "Security"
        DRIVER = "DRIVER", "Driver"
        NURSE = "NURSE", "School nurse"
        LIBRARIAN = "LIBRARIAN", "Librarian"
        GROUNDS = "GROUNDS", "Grounds keeper"
        OTHER = "OTHER", "Other"

    class EmploymentType(models.TextChoices):
        BOM = "BOM", "BOM employed"
        PTA = "PTA", "PTA employed"
        CONTRACT = "CONTRACT", "Contracted"
        COUNTY = "COUNTY", "County/Government"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="support_profile",
        help_text="Portal login for this staff member (role SUPPORT)",
    )
    supervisor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="supervises_support",
        help_text="Who this staff member reports to",
    )
    photo = models.ImageField(upload_to="staff_photos/", null=True, blank=True)
    full_name = models.CharField(max_length=150)
    category = models.CharField(max_length=10, choices=Category.choices)
    title = models.CharField(
        max_length=100, blank=True, help_text="Rank/title, e.g. Head Cook, Chief Security Officer"
    )
    phone = models.CharField(max_length=15, blank=True)
    employment_type = models.CharField(
        max_length=8, choices=EmploymentType.choices, default=EmploymentType.BOM
    )
    active = models.BooleanField(default=True)
    extra = models.JSONField(
        default=dict, blank=True, help_text="Values for admin-defined staff columns"
    )

    class Meta:
        ordering = ["category", "full_name", "id"]
        verbose_name_plural = "support staff"

    def __str__(self):
        return f"{self.full_name} ({self.get_category_display()})"


class Duty(SchoolScopedModel):
    """An extra responsibility a staff member carries beyond their post —
    games master, exams coordinator, fire marshal, and so on."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="duties"
    )
    title = models.CharField(max_length=120)
    description = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = "duties"
        ordering = ["title"]

    def __str__(self):
        return f"{self.title} — {self.user.get_full_name() or self.user.username}"


class StaffReport(SchoolScopedModel):
    """A report a staff member submits up their reporting line.

    Draft → Submitted → Approved / Returned. The supervisor recorded on the
    staff profile is the one who reviews it.
    """

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SUBMITTED = "SUBMITTED", "Submitted"
        APPROVED = "APPROVED", "Approved"
        RETURNED = "RETURNED", "Returned for changes"

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="staff_reports"
    )
    supervisor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reports_to_review",
    )
    title = models.CharField(max_length=150)
    period = models.CharField(max_length=60, blank=True, help_text="e.g. Term 2 2026, June")
    body = models.TextField(blank=True)
    document = models.FileField(upload_to="reports/%Y/", null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_reports",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_comment = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"


class StaffTask(SchoolScopedModel):
    """Work a supervisor assigns to someone who reports to them."""

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        IN_PROGRESS = "DOING", "In progress"
        DONE = "DONE", "Done"

    class Priority(models.TextChoices):
        NORMAL = "NORMAL", "Normal"
        HIGH = "HIGH", "High"

    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="staff_tasks"
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tasks_assigned"
    )
    title = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    due_date = models.DateField(null=True, blank=True)
    priority = models.CharField(
        max_length=6, choices=Priority.choices, default=Priority.NORMAL
    )
    status = models.CharField(max_length=5, choices=Status.choices, default=Status.OPEN)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["status", "due_date", "-created_at"]

    def __str__(self):
        return f"{self.title} → {self.assigned_to.get_full_name() or self.assigned_to.username}"


class StaffMessage(SchoolScopedModel):
    """A note between a staff member and their supervisor."""

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_messages"
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="received_messages"
    )
    body = models.TextField()
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.sender} → {self.recipient}: {self.body[:40]}"


class StaffField(SchoolScopedModel):
    """An extra column the admin adds to the staff register.

    Values live in Teacher.extra / SupportStaff.extra keyed by `key`, so a
    school can track things we didn't model (ID number, date joined, NSSF no)
    without a schema change.
    """

    class AppliesTo(models.TextChoices):
        ALL = "ALL", "All staff"
        TEACHING = "TEACHING", "Teaching staff"
        NON_TEACHING = "NON_TEACHING", "Non-teaching staff"

    label = models.CharField(max_length=50)
    key = models.SlugField(max_length=50)
    applies_to = models.CharField(
        max_length=12, choices=AppliesTo.choices, default=AppliesTo.ALL
    )
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["school", "key"], name="unique_staff_field_key")
        ]

    def __str__(self):
        return f"{self.label} ({self.get_applies_to_display()})"


class SchemeOfWork(SchoolScopedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PENDING = "PENDING", "Pending review"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    class Source(models.TextChoices):
        MANUAL = "MANUAL", "Entered manually"
        UPLOADED = "UPLOADED", "Uploaded document"
        GENERATED = "GENERATED", "AI generated"

    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE, related_name="schemes")
    learning_area = models.ForeignKey("assessments.LearningArea", on_delete=models.CASCADE)
    grade = models.IntegerField()
    term = models.PositiveSmallIntegerField()
    year = models.PositiveSmallIntegerField()
    content = models.JSONField(
        default=dict, blank=True, help_text="Weeks -> strands/sub-strands plan"
    )
    document = models.FileField(
        upload_to="schemes/%Y/", null=True, blank=True, help_text="Uploaded scheme document"
    )
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.MANUAL)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    reviewed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_schemes",
        help_text="Admin/head who approved or rejected",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_comment = models.TextField(blank=True)

    class Meta:
        ordering = ["-year", "-term", "grade", "id"]

    def __str__(self):
        return f"SoW {self.learning_area} G{self.grade} T{self.term} {self.year}"


class LessonPlan(SchoolScopedModel):
    scheme = models.ForeignKey(SchemeOfWork, on_delete=models.CASCADE, related_name="lesson_plans")
    week = models.PositiveSmallIntegerField()
    lesson_number = models.PositiveSmallIntegerField()
    strand = models.CharField(max_length=100)
    sub_strand = models.CharField(max_length=100, blank=True)
    learning_outcomes = models.TextField()
    resources = models.TextField(blank=True)

    class Meta:
        ordering = ["week", "lesson_number"]

    def __str__(self):
        return f"{self.scheme} wk{self.week} lesson {self.lesson_number}"


class TeacherAttendance(SchoolScopedModel):
    class Status(models.TextChoices):
        PRESENT = "P", "Present"
        ABSENT = "A", "Absent"
        LEAVE = "L", "On leave"

    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE, related_name="attendance")
    date = models.DateField()
    status = models.CharField(max_length=1, choices=Status.choices, default=Status.PRESENT)

    class Meta:
        ordering = ["-date", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["teacher", "date"], name="one_teacher_attendance_per_day"
            )
        ]

    def __str__(self):
        return f"{self.teacher} {self.date}: {self.get_status_display()}"


class ProfessionalDevelopmentRecord(SchoolScopedModel):
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE, related_name="pd_records")
    title = models.CharField(max_length=200)
    provider = models.CharField(max_length=100, blank=True, help_text="e.g. TSC, KICD")
    completed_on = models.DateField()
    tpd_points = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["-completed_on", "id"]

    def __str__(self):
        return f"{self.teacher} — {self.title}"
