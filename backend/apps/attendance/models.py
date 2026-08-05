from django.db import models

from apps.common.models import SchoolScopedModel


class AttendanceRecord(SchoolScopedModel):
    class Status(models.TextChoices):
        PRESENT = "P", "Present"
        ABSENT = "A", "Absent"
        LATE = "L", "Late"
        EXCUSED = "E", "Excused"

    learner = models.ForeignKey(
        "students.Learner", on_delete=models.CASCADE, related_name="attendance"
    )
    date = models.DateField()
    status = models.CharField(max_length=1, choices=Status.choices, default=Status.PRESENT)
    recorded_by = models.ForeignKey(
        "teachers.Teacher", on_delete=models.SET_NULL, null=True, blank=True
    )

    class Meta:
        ordering = ["-date", "learner_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["learner", "date"], name="one_attendance_per_learner_per_day"
            )
        ]

    def __str__(self):
        return f"{self.learner} {self.date}: {self.get_status_display()}"
