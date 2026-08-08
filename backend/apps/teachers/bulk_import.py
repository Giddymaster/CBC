"""Bulk staff import from a spreadsheet.

The whole staff room in one file — teaching and non-teaching rows side by side,
told apart by a Type column. Mirrors the learner importer's manners: flexible
headers, a dry run that reports row-numbered problems, and nothing written
until a second call commits.

Teaching rows create the portal login too; the generated passwords come back
once in the commit response, for the admin to hand out.
"""

import csv
import io
import secrets

from django.contrib.auth import get_user_model
from django.db import transaction

from apps.assessments.models import LearningArea
from apps.schools.moe import ALL_GRADES, GRADE_LABELS
from apps.students.models import ClassGroup

from .models import SupportStaff, Teacher

User = get_user_model()

COLUMNS = {
    "type": ["type", "staff type", "kind"],
    "first_name": ["first name", "firstname", "given name"],
    "last_name": ["last name", "lastname", "surname"],
    "full_name": ["full name", "name"],
    "gender": ["gender", "sex"],
    "tsc_number": [
        "tsc", "tsc number", "tsc no", "tsc / payroll no", "payroll no",
        "payroll number", "staff no", "staff number",
    ],
    "phone": ["phone", "telephone", "mobile", "phone number"],
    "employment": ["employment", "employment type", "employer", "terms"],
    "category": ["category", "department", "section"],
    "rank_title": ["rank", "title", "rank / title", "rank/title", "position"],
    "subjects": ["subjects", "learning areas", "subject"],
    "class_teacher_of": [
        "class teacher of", "class teacher", "class", "class assigned",
    ],
}

GENDERS = {"m": "M", "male": "M", "f": "F", "female": "F", "o": "O", "other": "O"}

TEACHING_WORDS = ("teaching", "teacher", "tsc")
RANKS = {
    "head": "HEAD", "head teacher": "HEAD", "headteacher": "HEAD",
    "deputy": "DEPUTY", "deputy head": "DEPUTY", "deputy head teacher": "DEPUTY",
    "senior": "SENIOR", "senior teacher": "SENIOR",
    "teacher": "TEACHER", "intern": "INTERN", "intern teacher": "INTERN",
}
TEACHING_EMPLOYMENT = {
    "tsc": "TSC", "government": "TSC", "government (tsc)": "TSC",
    "pnp": "PNP", "bom": "BOM", "bom employed": "BOM",
    "pta": "PTA", "pta employed": "PTA",
}
SUPPORT_EMPLOYMENT = {
    "bom": "BOM", "bom employed": "BOM", "pta": "PTA", "pta employed": "PTA",
    "contract": "CONTRACT", "contracted": "CONTRACT",
    "county": "COUNTY", "government": "COUNTY", "county/government": "COUNTY",
}
# Keyword → SupportStaff.Category, tried in order.
SUPPORT_CATEGORIES = [
    ("bursar", "BURSAR"), ("account", "BURSAR"),
    ("secretary", "SECRETARY"), ("admin", "SECRETARY"),
    ("kitchen", "KITCHEN"), ("cook", "KITCHEN"),
    ("clean", "CLEANER"),
    ("security", "SECURITY"), ("watchman", "SECURITY"), ("guard", "SECURITY"),
    ("driver", "DRIVER"), ("transport", "DRIVER"),
    ("nurse", "NURSE"), ("health", "NURSE"),
    ("libra", "LIBRARIAN"),
    ("ground", "GROUNDS"),
]

GRADE_WORDS = {label.lower(): value for value, label in GRADE_LABELS.items()}
GRADE_WORDS.update({f"g{v}": v for v in ALL_GRADES if v > 0})
GRADE_WORDS.update({str(v): v for v in ALL_GRADES if v > 0})


def _map_headers(fieldnames):
    mapping = {}
    for header in fieldnames or []:
        cleaned = (header or "").strip().lower().replace("_", " ")
        for field, spellings in COLUMNS.items():
            if cleaned in spellings:
                mapping[header] = field
                break
    return mapping


def _parse_class(value):
    """'G4 North' -> (4, 'North'); 'PP1' -> (-1, ''). None means not set."""
    text = (value or "").strip()
    if not text:
        return None, None, None
    parts = text.split(None, 1)
    grade_word = parts[0].strip().lower()
    if grade_word not in GRADE_WORDS:
        return None, None, f"'{parts[0]}' is not a grade"
    stream = parts[1].strip() if len(parts) > 1 else ""
    return GRADE_WORDS[grade_word], stream, None


def parse(file_obj):
    """Read the upload into (rows, errors, mapping). Touches no database."""
    raw = file_obj.read()
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            raw = raw.decode("cp1252", errors="replace")
    reader = csv.DictReader(io.StringIO(raw))
    mapping = _map_headers(reader.fieldnames)
    if "type" not in mapping.values():
        return [], [{
            "row": 0,
            "errors": [
                "no Type column found — each row needs Teaching or Non-teaching"
            ],
        }], mapping

    rows, errors = [], []
    known_areas = {a.name.lower(): a for a in LearningArea.objects.all()}
    for index, raw_row in enumerate(reader, start=2):
        record = {"_row": index}
        for header, value in raw_row.items():
            field = mapping.get(header)
            if field:
                record[field] = (value or "").strip()

        problems = []
        kind_text = record.get("type", "").lower()
        teaching = any(w in kind_text for w in TEACHING_WORDS) and "non" not in kind_text
        record["_teaching"] = teaching

        # Name: first+last, or a full name split on the first space.
        first = record.get("first_name", "")
        last = record.get("last_name", "")
        if not (first and last) and record.get("full_name"):
            bits = record["full_name"].split(None, 1)
            first = first or bits[0]
            last = last or (bits[1] if len(bits) > 1 else "")
        if not first:
            problems.append("a name is missing")
        record["first_name"], record["last_name"] = first, last

        gender = GENDERS.get(record.get("gender", "").lower(), "")
        record["gender"] = gender

        if teaching:
            if not record.get("tsc_number"):
                problems.append("teaching staff need a TSC / payroll number")
            rank_text = record.get("rank_title", "").strip().lower()
            record["rank"] = RANKS.get(rank_text, "TEACHER")
            emp_text = record.get("employment", "").strip().lower()
            record["employment_type"] = TEACHING_EMPLOYMENT.get(emp_text, "TSC")
            # Subjects: semicolon- or comma-separated learning-area names.
            names = [
                s.strip()
                for s in record.get("subjects", "").replace(";", ",").split(",")
                if s.strip()
            ]
            record["_areas"], unknown = [], []
            for name in names:
                area = known_areas.get(name.lower())
                (record["_areas"].append(area) if area else unknown.append(name))
            if unknown:
                problems.append(
                    f"unknown learning area(s): {', '.join(unknown)} — "
                    "define them under School (Grades) first"
                )
            grade, stream, err = _parse_class(record.get("class_teacher_of"))
            if err:
                problems.append(f"class teacher of: {err}")
            record["_class"] = None if grade is None else (grade, stream)
        else:
            cat_text = (
                record.get("category", "") + " " + record.get("rank_title", "")
            ).lower()
            record["support_category"] = next(
                (code for word, code in SUPPORT_CATEGORIES if word in cat_text),
                "OTHER",
            )
            emp_text = record.get("employment", "").strip().lower()
            record["employment_type"] = SUPPORT_EMPLOYMENT.get(emp_text, "BOM")
            if record.get("class_teacher_of"):
                problems.append("only teaching staff can be class teachers")

        if problems:
            errors.append({
                "row": index,
                "name": f"{first} {last}".strip(),
                "errors": problems,
            })
        else:
            rows.append(record)
    return rows, errors, mapping


def check_against_register(rows, school):
    """Flag duplicates against existing staff and within the file itself."""
    existing_tsc = {
        t.lower()
        for t in Teacher.objects.values_list("tsc_number", flat=True)
    }
    existing_support = {
        n.lower()
        for n in SupportStaff.objects.filter(school=school).values_list(
            "full_name", flat=True
        )
    }
    clean, clashes, seen_tsc = [], [], set()
    for r in rows:
        name = f"{r['first_name']} {r['last_name']}".strip()
        if r["_teaching"]:
            tsc = r["tsc_number"].lower()
            if tsc in existing_tsc:
                clashes.append({
                    "row": r["_row"], "name": name,
                    "errors": [f"TSC/payroll no {r['tsc_number']} is already on the register"],
                })
                continue
            if tsc in seen_tsc:
                clashes.append({
                    "row": r["_row"], "name": name,
                    "errors": [f"TSC/payroll no {r['tsc_number']} appears twice in this file"],
                })
                continue
            seen_tsc.add(tsc)
        elif name.lower() in existing_support:
            clashes.append({
                "row": r["_row"], "name": name,
                "errors": ["a non-teaching staff member with this name is already on the register"],
            })
            continue
        clean.append(r)
    return clean, clashes


def _unique_username(base):
    base = "".join(ch for ch in base.lower() if ch.isalnum()) or "staff"
    username, n = base, 1
    while User.objects.filter(username=username).exists():
        n += 1
        username = f"{base}{n}"
    return username


def commit(rows, *, school, user):
    """Write everything in one transaction. Returns (created_count, logins)."""
    logins = []
    with transaction.atomic():
        for r in rows:
            if r["_teaching"]:
                username = _unique_username(r["first_name"])
                password = secrets.token_urlsafe(8)
                account = User.objects.create_user(
                    username=username,
                    password=password,
                    first_name=r["first_name"],
                    last_name=r["last_name"],
                    role="TEACHER",
                    school=school,
                    phone=r.get("phone", ""),
                )
                account.must_change_password = True
                account.save(update_fields=["must_change_password"])
                teacher = Teacher.objects.create(
                    school=school,
                    user=account,
                    tsc_number=r["tsc_number"],
                    employment_type=r["employment_type"],
                    rank=r["rank"],
                    gender=r["gender"],
                )
                if r["_areas"]:
                    teacher.learning_areas.set(r["_areas"])
                if r["_class"] is not None:
                    grade, stream = r["_class"]
                    ClassGroup.objects.update_or_create(
                        school=school, grade=grade, stream=stream,
                        defaults={"class_teacher": teacher},
                    )
                logins.append({
                    "name": account.get_full_name(),
                    "username": username,
                    "password": password,
                })
            else:
                SupportStaff.objects.create(
                    school=school,
                    full_name=f"{r['first_name']} {r['last_name']}".strip(),
                    gender=r["gender"],
                    category=r["support_category"],
                    title=r.get("rank_title", ""),
                    employment_type=r["employment_type"],
                    phone=r.get("phone", ""),
                )
    return len(rows), logins


def template_csv():
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([
        "Type", "First Name", "Last Name", "Gender", "TSC / Payroll No",
        "Phone", "Employment", "Category", "Rank / Title", "Subjects",
        "Class Teacher Of",
    ])
    writer.writerow([
        "Teaching", "Jane", "Wanjiku", "F", "412001", "254700000001",
        "TSC", "", "Senior Teacher", "Mathematics; Integrated Science",
        "G4 North",
    ])
    writer.writerow([
        "Non-teaching", "Esther", "Nafula", "F", "", "254700000002",
        "BOM", "Kitchen staff", "Head Cook", "", "",
    ])
    return out.getvalue()
