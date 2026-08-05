from django.core.exceptions import ValidationError
from django.db import models

from apps.common.models import SchoolScopedModel


class Room(SchoolScopedModel):
    name = models.CharField(max_length=50)
    is_lab = models.BooleanField(default=False)
    capacity = models.PositiveSmallIntegerField(default=40)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Period(SchoolScopedModel):
    """A slot in the school day, e.g. period 1 = 08:00-08:40."""

    number = models.PositiveSmallIntegerField()
    start_time = models.TimeField()
    end_time = models.TimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["school", "number"], name="unique_period_per_school")
        ]
        ordering = ["number"]

    def __str__(self):
        return f"P{self.number} ({self.start_time:%H:%M}-{self.end_time:%H:%M})"


class Lesson(SchoolScopedModel):
    class Day(models.IntegerChoices):
        MON = 1, "Monday"
        TUE = 2, "Tuesday"
        WED = 3, "Wednesday"
        THU = 4, "Thursday"
        FRI = 5, "Friday"

    day = models.IntegerField(choices=Day.choices)
    period = models.ForeignKey(Period, on_delete=models.CASCADE)
    teacher = models.ForeignKey("teachers.Teacher", on_delete=models.CASCADE, related_name="lessons")
    learning_area = models.ForeignKey("assessments.LearningArea", on_delete=models.CASCADE)
    grade = models.IntegerField()
    stream = models.CharField(max_length=20, blank=True)
    room = models.ForeignKey(Room, on_delete=models.SET_NULL, null=True, blank=True)

    def clean(self):
        """Reject double-bookings: same slot can't reuse the teacher, the room,
        or the class (grade+stream). This is the clash detection the auto-
        generator will also build on."""
        clashes = Lesson.objects.filter(school=self.school, day=self.day, period=self.period)
        if self.pk:
            clashes = clashes.exclude(pk=self.pk)

        if clashes.filter(teacher=self.teacher).exists():
            raise ValidationError({"teacher": "Teacher is already booked in this slot."})
        if self.room and clashes.filter(room=self.room).exists():
            raise ValidationError({"room": "Room is already in use in this slot."})
        if clashes.filter(grade=self.grade, stream=self.stream).exists():
            raise ValidationError({"stream": "This class already has a lesson in this slot."})

    class Meta:
        ordering = ["day", "period__number", "grade", "stream"]

    def __str__(self):
        return f"{self.get_day_display()} {self.period} G{self.grade}{self.stream} {self.learning_area}"


class LessonRequirement(SchoolScopedModel):
    """What the timetable generator must place: N lessons/week of a learning
    area for a class, taught by a teacher, optionally needing a lab."""

    teacher = models.ForeignKey("teachers.Teacher", on_delete=models.CASCADE)
    learning_area = models.ForeignKey("assessments.LearningArea", on_delete=models.CASCADE)
    grade = models.IntegerField()
    stream = models.CharField(max_length=20, blank=True)
    lessons_per_week = models.PositiveSmallIntegerField(default=5)
    needs_lab = models.BooleanField(default=False)

    class Meta:
        ordering = ["grade", "stream", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "teacher", "learning_area", "grade", "stream"],
                name="unique_lesson_requirement",
            )
        ]

    def __str__(self):
        return (
            f"{self.learning_area} G{self.grade}{self.stream}: "
            f"{self.lessons_per_week}/wk ({self.teacher})"
        )
