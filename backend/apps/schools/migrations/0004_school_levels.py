"""Replace the single `level` (with its catch-all "Composite") with a `levels`
list, so a school can record every level it actually offers.

Existing rows are carried over: a "COMPOSITE" school becomes all three levels,
and any other value becomes a single-item list.
"""

from django.db import migrations, models

_ALL = ["PRIMARY", "JSS", "SSS"]


def level_to_levels(apps, schema_editor):
    School = apps.get_model("schools", "School")
    for school in School.objects.all():
        old = (school.level or "").strip().upper()
        if old == "COMPOSITE":
            school.levels = list(_ALL)
        elif old:
            school.levels = [old]
        else:
            school.levels = []
        school.save(update_fields=["levels"])


def levels_to_level(apps, schema_editor):
    School = apps.get_model("schools", "School")
    for school in School.objects.all():
        chosen = list(school.levels or [])
        if len(chosen) > 1:
            school.level = "COMPOSITE"
        elif chosen:
            school.level = chosen[0]
        else:
            school.level = "JSS"
        school.save(update_fields=["level"])


class Migration(migrations.Migration):
    dependencies = [
        ("schools", "0003_school_accommodation_school_category_school_gender_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="school",
            name="levels",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Any of PRIMARY / JSS / SSS — the levels the school offers",
            ),
        ),
        migrations.RunPython(level_to_levels, levels_to_level),
        migrations.RemoveField(model_name="school", name="level"),
    ]
