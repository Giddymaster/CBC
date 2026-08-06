"""Bulk learner import from a spreadsheet.

A January intake of two hundred is unworkable one admission form at a time, and
schools already keep their register in Excel. This takes that file.

Two things make it safe to hand to a school secretary:

- **Dry run first.** The upload is parsed, validated row by row, and reported
  back with the errors *before* anything is written. Nothing is created until a
  second call says commit.
- **Row numbers in every error.** "Row 47: date of birth 31/02/2019 is not a
  real date" is actionable; "invalid input" is not.
"""

import csv
import io
from datetime import datetime

from django.db import transaction

from apps.schools.moe import ALL_GRADES, GRADE_LABELS

from .admissions import next_admission_number
from .models import Guardian, Learner

# Accepted spellings for each column. Schools do not agree on headers, and
# rejecting a file because it says "Adm No" rather than "admission_number"
# would send the secretary back to Excel for no reason.
COLUMNS = {
    "admission_number": ["admission number", "admission no", "adm no", "adm", "admno"],
    "upi": ["upi", "upi number", "nemis", "nemis number"],
    "first_name": ["first name", "firstname", "given name"],
    "middle_name": ["middle name", "middlename", "other name", "other names"],
    "last_name": ["last name", "lastname", "surname", "family name"],
    "date_of_birth": ["date of birth", "dob", "birth date", "birthdate"],
    "gender": ["gender", "sex"],
    "grade": ["grade", "class", "form"],
    "stream": ["stream", "section"],
    "guardian_name": ["guardian", "guardian name", "parent", "parent name"],
    "guardian_phone": ["guardian phone", "parent phone", "phone", "telephone", "mobile"],
    "guardian_relationship": ["relationship", "guardian relationship"],
}

DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d"]

GENDERS = {
    "m": "M", "male": "M", "boy": "M",
    "f": "F", "female": "F", "girl": "F",
}

# "PP1", "Grade 4", "4", "G4" all mean the same thing to a school.
GRADE_WORDS = {label.lower(): value for value, label in GRADE_LABELS.items()}
GRADE_WORDS.update({f"g{v}": v for v in ALL_GRADES if v > 0})
GRADE_WORDS.update({str(v): v for v in ALL_GRADES if v > 0})


def _map_headers(fieldnames):
    """Actual header -> our field name, for the headers we recognise."""
    mapping = {}
    for header in fieldnames or []:
        cleaned = (header or "").strip().lower().replace("_", " ")
        for field, spellings in COLUMNS.items():
            if cleaned in spellings:
                mapping[header] = field
                break
    return mapping


def _parse_date(value):
    text = (value or "").strip()
    if not text:
        return None, "date of birth is missing"
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date(), None
        except ValueError:
            continue
    return None, f"'{text}' is not a date we recognise (try YYYY-MM-DD or DD/MM/YYYY)"


def _parse_grade(value):
    text = (value or "").strip().lower()
    if not text:
        return None, "grade is missing"
    if text in GRADE_WORDS:
        return GRADE_WORDS[text], None
    try:
        number = int(float(text))
    except ValueError:
        return None, f"'{value}' is not a grade"
    if number not in ALL_GRADES:
        return None, f"grade {number} is outside PG to Grade 12"
    return number, None


def parse(file_obj):
    """Read the upload into (rows, errors, headers). Touches no database."""
    raw = file_obj.read()
    if isinstance(raw, bytes):
        # Excel on Windows commonly writes cp1252; fall back rather than fail.
        for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
            try:
                text = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            return [], [{"row": 0, "errors": ["could not read the file's text encoding"]}], {}
    else:
        text = raw

    reader = csv.DictReader(io.StringIO(text))
    mapping = _map_headers(reader.fieldnames)
    missing = {"first_name", "last_name", "grade"} - set(mapping.values())
    if missing:
        return [], [
            {
                "row": 0,
                "errors": [
                    (
                        "the file needs at least a first name, last name and grade "
                        f"column (missing: {', '.join(sorted(missing))})"
                    )
                ],
            }
        ], mapping

    rows, errors = [], []
    seen_numbers = set()
    # Row 1 is the header, so data starts at 2 — matching what the secretary
    # sees in Excel.
    for index, raw_row in enumerate(reader, start=2):
        record = {
            field: (raw_row.get(header) or "").strip()
            for header, field in mapping.items()
        }
        problems = []

        if not record.get("first_name"):
            problems.append("first name is missing")
        if not record.get("last_name"):
            problems.append("last name is missing")

        dob, error = _parse_date(record.get("date_of_birth"))
        if error:
            problems.append(error)
        record["date_of_birth"] = dob

        grade, error = _parse_grade(record.get("grade"))
        if error:
            problems.append(error)
        record["grade"] = grade

        gender = GENDERS.get((record.get("gender") or "").strip().lower())
        if gender is None:
            problems.append("gender should be M or F")
        record["gender"] = gender

        number = record.get("admission_number", "")
        if number:
            if number.lower() in seen_numbers:
                problems.append(f"admission number {number} appears twice in this file")
            seen_numbers.add(number.lower())

        if problems:
            errors.append({"row": index, "name": _display_name(record), "errors": problems})
        else:
            record["_row"] = index
            rows.append(record)

    return rows, errors, mapping


def _display_name(record):
    return " ".join(
        filter(None, [record.get("first_name"), record.get("last_name")])
    ) or "(no name)"


def check_against_register(rows, school):
    """Flag rows that clash with learners already enrolled."""
    taken = {
        n.lower()
        for n in Learner.objects.filter(school=school).values_list(
            "admission_number", flat=True
        )
    }
    clashes = []
    for row in rows:
        number = row.get("admission_number", "")
        if number and number.lower() in taken:
            clashes.append(
                {
                    "row": row["_row"],
                    "name": _display_name(row),
                    "errors": [f"admission number {number} is already enrolled"],
                }
            )
    clash_rows = {c["row"] for c in clashes}
    return [r for r in rows if r["_row"] not in clash_rows], clashes


def commit(rows, *, school, user):
    """Create the learners. All or nothing."""
    created = []
    with transaction.atomic():
        for row in rows:
            number = row.get("admission_number") or next_admission_number(school)
            learner = Learner.objects.create(
                school=school,
                admission_number=number,
                upi=row.get("upi", ""),
                first_name=row["first_name"],
                middle_name=row.get("middle_name", ""),
                last_name=row["last_name"],
                date_of_birth=row["date_of_birth"],
                gender=row["gender"],
                grade=row["grade"],
                stream=row.get("stream", ""),
                admitted_by=user,
            )
            name = row.get("guardian_name", "")
            phone = row.get("guardian_phone", "")
            if name and phone:
                guardian = Guardian.objects.filter(
                    school=school, phone=phone, full_name__iexact=name
                ).first()
                if guardian is None:
                    guardian = Guardian.objects.create(
                        school=school,
                        full_name=name,
                        phone=phone,
                        relationship=row.get("guardian_relationship", ""),
                        is_primary_contact=True,
                    )
                learner.guardians.add(guardian)
            created.append(learner)
    return created


TEMPLATE_HEADERS = [
    "Admission No", "UPI", "First Name", "Middle Name", "Last Name",
    "Date of Birth", "Gender", "Grade", "Stream",
    "Guardian Name", "Guardian Phone", "Relationship",
]


def template_csv():
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(TEMPLATE_HEADERS)
    writer.writerow(
        ["", "", "Wanjiru", "", "Kamau", "2019-04-12", "F", "Grade 1", "North",
         "Grace Kamau", "254722000111", "MOTHER"]
    )
    return buffer.getvalue()
