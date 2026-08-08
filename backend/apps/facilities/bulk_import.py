"""Bulk facilities import from a spreadsheet.

Categories are created as they appear, and a Staff Assigned column posts the
named staff to the facility — matched by name against the register, teaching
or non-teaching — so the school's whole plant lands in one upload.
"""

import csv
import io

from django.db import transaction

from apps.teachers.models import SupportStaff, Teacher

from .models import Facility, FacilityAssignment, FacilityCategory

COLUMNS = {
    "name": ["facility", "name", "facility name"],
    "category": ["category", "department", "section"],
    "location": ["location", "where"],
    "capacity": ["capacity", "seats", "beds"],
    "details": ["details", "notes", "description"],
    "condition": ["condition", "state"],
    "staff": ["staff assigned", "staff", "assigned staff", "personnel"],
}


def _map_headers(fieldnames):
    mapping = {}
    for header in fieldnames or []:
        cleaned = (header or "").strip().lower().replace("_", " ")
        for field, spellings in COLUMNS.items():
            if cleaned in spellings:
                mapping[header] = field
                break
    return mapping


def _staff_lookup(school):
    """Name (lowercased) → ('teacher'|'support', instance)."""
    lookup = {}
    for t in Teacher.objects.filter(school=school).select_related("user"):
        name = (t.user.get_full_name() or t.user.username).lower()
        lookup[name] = ("teacher", t)
    for s in SupportStaff.objects.filter(school=school):
        lookup[s.full_name.lower()] = ("support", s)
    return lookup


def parse(file_obj, school):
    raw = file_obj.read()
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            raw = raw.decode("cp1252", errors="replace")
    reader = csv.DictReader(io.StringIO(raw))
    mapping = _map_headers(reader.fieldnames)
    if "name" not in mapping.values():
        return [], [{
            "row": 0, "errors": ["no Facility/Name column found"],
        }], mapping

    staff = _staff_lookup(school)
    existing = {
        n.lower()
        for n in Facility.objects.filter(school=school).values_list("name", flat=True)
    }
    rows, errors, seen = [], [], set()
    for index, raw_row in enumerate(reader, start=2):
        record = {"_row": index}
        for header, value in raw_row.items():
            field = mapping.get(header)
            if field:
                record[field] = (value or "").strip()

        problems = []
        name = record.get("name", "")
        if not name:
            problems.append("the facility has no name")
        elif name.lower() in existing:
            problems.append(f"'{name}' is already on the facilities register")
        elif name.lower() in seen:
            problems.append(f"'{name}' appears twice in this file")
        if not record.get("category"):
            problems.append("a category is missing (e.g. Classrooms, Transport)")

        capacity = record.get("capacity", "")
        if capacity:
            try:
                record["capacity"] = int(float(capacity))
            except ValueError:
                problems.append(f"capacity '{capacity}' is not a number")
        else:
            record["capacity"] = None

        # Staff names, semicolon- or comma-separated; each must be on the register.
        record["_staff"], missing = [], []
        for person in (
            record.get("staff", "").replace(";", ",").split(",")
        ):
            person = person.strip()
            if not person:
                continue
            hit = staff.get(person.lower())
            (record["_staff"].append((person, hit)) if hit else missing.append(person))
        if missing:
            problems.append(
                f"not on the staff register: {', '.join(missing)} — import staff first"
            )

        if problems:
            errors.append({"row": index, "name": name, "errors": problems})
        else:
            seen.add(name.lower())
            rows.append(record)
    return rows, errors, mapping


def commit(rows, *, school):
    created = 0
    with transaction.atomic():
        for r in rows:
            category, _ = FacilityCategory.objects.get_or_create(
                school=school, name=r["category"]
            )
            notes = r.get("details", "")
            if r.get("condition"):
                notes = f"{notes}\nCondition: {r['condition']}".strip()
            facility = Facility.objects.create(
                school=school,
                name=r["name"],
                category=category,
                location=r.get("location", ""),
                capacity=r.get("capacity"),
                notes=notes,
            )
            for person_name, (kind, instance) in r["_staff"]:
                FacilityAssignment.objects.create(
                    school=school,
                    facility=facility,
                    teacher=instance if kind == "teacher" else None,
                    support_staff=instance if kind == "support" else None,
                    position=(
                        instance.title
                        if kind == "support" and instance.title
                        else "Assigned staff"
                    ),
                )
            created += 1
    return created


def template_csv():
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([
        "Facility", "Category", "Location", "Capacity", "Details",
        "Condition", "Staff Assigned",
    ])
    writer.writerow([
        "Science Laboratory", "Laboratories", "Block C", "40",
        "Integrated Science practicals", "Good", "George Kamau",
    ])
    return out.getvalue()
