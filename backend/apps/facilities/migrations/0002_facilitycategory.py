"""Turn the fixed facility_type enum into an editable FacilityCategory table.

Existing facilities keep their grouping: each old type value becomes a
category (renamed where the school asked for it — Sick Bay is now Infirmary,
and the groupings are plural since they hold several facilities).
"""

import django.db.models.deletion
from django.db import migrations, models

# old facility_type value -> new category name
TYPE_TO_CATEGORY = {
    "KITCHEN": "Kitchen & Dining",
    "HEALTH": "Infirmary",
    "TRANSPORT": "Transport",
    "DORMITORY": "Dormitories",
    "LAB": "Laboratories",
    "ICT": "Computer Labs / ICT",
    "LIBRARY": "Libraries",
    "SPORTS": "Sports & Games",
    "FARM": "Farm / Agriculture",
    "WORKSHOP": "Workshops",
    "HOME_SCI": "Home Science",
    "STORE": "Stores",
    "SANITATION": "Water & Sanitation",
    "GROUNDS": "Grounds & Maintenance",
    "ADMIN": "Administration",
    "STAFFROOM": "Staff Room",
    "OTHER": "Other",
}
ORDER = list(TYPE_TO_CATEGORY.values())


def build_categories(apps, schema_editor):
    Facility = apps.get_model("facilities", "Facility")
    FacilityCategory = apps.get_model("facilities", "FacilityCategory")

    for facility in Facility.objects.all():
        name = TYPE_TO_CATEGORY.get(facility.facility_type, "Other")
        category, _ = FacilityCategory.objects.get_or_create(
            school_id=facility.school_id,
            name=name,
            defaults={"order": ORDER.index(name) if name in ORDER else 99},
        )
        facility.category = category
        facility.save(update_fields=["category"])


def restore_types(apps, schema_editor):
    Facility = apps.get_model("facilities", "Facility")
    reverse = {v: k for k, v in TYPE_TO_CATEGORY.items()}
    for facility in Facility.objects.select_related("category"):
        facility.facility_type = reverse.get(facility.category.name, "OTHER")
        facility.save(update_fields=["facility_type"])


class Migration(migrations.Migration):
    dependencies = [
        ("schools", "0001_initial"),
        ("facilities", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="FacilityCategory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=60)),
                ("order", models.PositiveSmallIntegerField(default=0)),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="facilitycategorys",
                        to="schools.school",
                    ),
                ),
            ],
            options={"verbose_name_plural": "facility categories", "ordering": ["order", "name"]},
        ),
        migrations.AddConstraint(
            model_name="facilitycategory",
            constraint=models.UniqueConstraint(
                fields=("school", "name"), name="unique_facility_category"
            ),
        ),
        migrations.AddField(
            model_name="facility",
            name="category",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="facilities",
                to="facilities.facilitycategory",
            ),
        ),
        migrations.RunPython(build_categories, restore_types),
        migrations.AlterField(
            model_name="facility",
            name="category",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="facilities",
                to="facilities.facilitycategory",
            ),
        ),
        migrations.RemoveField(model_name="facility", name="facility_type"),
        migrations.AlterModelOptions(
            name="facility",
            options={
                "ordering": ["category__order", "category__name", "name"],
                "verbose_name_plural": "facilities",
            },
        ),
    ]
