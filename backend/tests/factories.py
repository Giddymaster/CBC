"""Small hand-rolled factories.

Deliberately not `factory_boy`: the graph is shallow and explicit fixtures make
the tenancy tests easier to read — you can see exactly which school owns what.
"""

from datetime import date

from django.contrib.auth import get_user_model

from apps.assessments.models import Assessment, LearningArea
from apps.schools.models import School
from apps.students.models import Guardian, Learner
from apps.teachers.models import SupportStaff, Teacher

User = get_user_model()

_counter = {"n": 0}


def _next():
    _counter["n"] += 1
    return _counter["n"]


def make_school(name="Test School", **kwargs):
    n = _next()
    return School.objects.create(
        name=name,
        code=kwargs.pop("code", f"SCH{n:04d}"),
        county=kwargs.pop("county", "Nairobi"),
        **kwargs,
    )


def make_user(school, role="TEACHER", username=None, **kwargs):
    n = _next()
    return User.objects.create_user(
        username=username or f"{role.lower()}{n}",
        password=kwargs.pop("password", "pass12345"),
        first_name=kwargs.pop("first_name", role.title()),
        last_name=kwargs.pop("last_name", f"User{n}"),
        role=role,
        school=school,
        **kwargs,
    )


def make_teacher(school, user=None, rank="TEACHER", supervisor=None, **kwargs):
    n = _next()
    user = user or make_user(school, "TEACHER")
    return Teacher.objects.create(
        school=school,
        user=user,
        tsc_number=kwargs.pop("tsc_number", f"TSC{n:06d}"),
        rank=rank,
        supervisor=supervisor,
        **kwargs,
    )


def make_support(school, category="KITCHEN", with_login=True, supervisor=None, **kwargs):
    n = _next()
    user = make_user(school, "SUPPORT") if with_login else None
    return SupportStaff.objects.create(
        school=school,
        user=user,
        full_name=kwargs.pop("full_name", f"Support {n}"),
        category=category,
        supervisor=supervisor,
        **kwargs,
    )


def make_learner(school, grade=5, **kwargs):
    n = _next()
    return Learner.objects.create(
        school=school,
        admission_number=kwargs.pop("admission_number", f"ADM{n:05d}"),
        first_name=kwargs.pop("first_name", "Learner"),
        last_name=kwargs.pop("last_name", f"Number{n}"),
        date_of_birth=kwargs.pop("date_of_birth", date(2015, 1, 1)),
        gender=kwargs.pop("gender", "M"),
        grade=grade,
        **kwargs,
    )


def make_guardian(school, learners=(), user=None, **kwargs):
    n = _next()
    guardian = Guardian.objects.create(
        school=school,
        user=user,
        full_name=kwargs.pop("full_name", f"Guardian {n}"),
        phone=kwargs.pop("phone", f"2547{n:08d}"),
        **kwargs,
    )
    for learner in learners:
        learner.guardians.add(guardian)
    return guardian


def make_learning_area(name=None, code=None, grades=None):
    n = _next()
    return LearningArea.objects.create(
        name=name or f"Subject {n}",
        code=code or f"SUB{n}",
        grades=grades if grades is not None else list(range(1, 13)),
    )


def make_assessment(school, learning_area=None, grade=5, **kwargs):
    return Assessment.objects.create(
        school=school,
        kind=kwargs.pop("kind", "CAT1"),
        learning_area=learning_area or make_learning_area(),
        grade=grade,
        term=kwargs.pop("term", 1),
        year=kwargs.pop("year", 2026),
        max_marks=kwargs.pop("max_marks", 100),
        **kwargs,
    )
