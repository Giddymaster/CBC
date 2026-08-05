from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models

from apps.common.models import SchoolScopedModel


class NavSection(SchoolScopedModel):
    """An admin-created heading in the sidebar, alongside the built-in ones
    (School, Learners, Academics, Finance). A section holds facility
    categories, so every entry under it opens a real page."""

    name = models.CharField(max_length=40)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]
        constraints = [
            models.UniqueConstraint(fields=["school", "name"], name="unique_nav_section")
        ]

    def __str__(self):
        return self.name


class FacilityCategory(SchoolScopedModel):
    """A department grouping — Transport, Dormitories, Libraries, Laboratories…

    Schools differ, so categories are data rather than a fixed list: the admin
    can add their own from the sidebar.
    """

    name = models.CharField(max_length=60)
    order = models.PositiveSmallIntegerField(default=0)
    section = models.ForeignKey(
        NavSection,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="categories",
        help_text="Sidebar heading this category sits under; blank = Facilities",
    )

    class Meta:
        verbose_name_plural = "facility categories"
        ordering = ["order", "name"]
        constraints = [
            models.UniqueConstraint(fields=["school", "name"], name="unique_facility_category")
        ]

    def __str__(self):
        return self.name


class Facility(SchoolScopedModel):
    """A physical facility inside a category — a specific bus, dormitory,
    library or lab. Carries the staff posted to it and the supplies it holds."""

    name = models.CharField(max_length=100)
    category = models.ForeignKey(
        FacilityCategory, on_delete=models.PROTECT, related_name="facilities"
    )
    location = models.CharField(max_length=100, blank=True)
    capacity = models.PositiveIntegerField(
        null=True, blank=True, help_text="Beds, seats, passengers — whatever fits this facility"
    )
    notes = models.TextField(blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "facilities"
        ordering = ["category__order", "category__name", "name"]
        constraints = [
            models.UniqueConstraint(fields=["school", "name"], name="unique_facility_name")
        ]

    def __str__(self):
        return self.name


class FacilityAssignment(SchoolScopedModel):
    """A staff member posted to a facility, with the position they hold there
    (Head Cook, Matron, Lab Technician, Driver...)."""

    facility = models.ForeignKey(
        Facility, on_delete=models.CASCADE, related_name="assignments"
    )
    teacher = models.ForeignKey(
        "teachers.Teacher", on_delete=models.CASCADE, null=True, blank=True,
        related_name="facility_assignments",
    )
    support_staff = models.ForeignKey(
        "teachers.SupportStaff", on_delete=models.CASCADE, null=True, blank=True,
        related_name="facility_assignments",
    )
    position = models.CharField(max_length=80, help_text="Role at this facility")

    def clean(self):
        if bool(self.teacher) == bool(self.support_staff):
            raise ValidationError(
                "Assign exactly one of teaching staff or non-teaching staff."
            )

    @property
    def staff_name(self):
        if self.teacher:
            return self.teacher.user.get_full_name() or self.teacher.user.username
        return self.support_staff.full_name if self.support_staff else ""

    class Meta:
        ordering = ["position", "id"]

    def __str__(self):
        return f"{self.staff_name} — {self.position} @ {self.facility}"


class Supply(SchoolScopedModel):
    """An item held by a facility. Status is derived from the quantity against
    the reorder level, so 'depleted' and 'running low' need no manual flag."""

    facility = models.ForeignKey(Facility, on_delete=models.CASCADE, related_name="supplies")
    item = models.CharField(max_length=100)
    unit = models.CharField(max_length=20, default="pcs", help_text="kg, litres, pcs, cartons")
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    reorder_level = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0"),
        help_text="Restock when the quantity falls to this level",
    )
    last_restocked = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name_plural = "supplies"
        ordering = ["item"]

    @property
    def status(self):
        if self.quantity <= 0:
            return "DEPLETED"
        if self.reorder_level and self.quantity <= self.reorder_level:
            return "LOW"
        return "IN_STOCK"

    def __str__(self):
        return f"{self.item} ({self.quantity} {self.unit}) @ {self.facility}"
