"""Seed a demo school with learners, assessments, fees — enough to click around.

Usage: python manage.py seed_demo
Creates/updates superuser 'admin' (password 'admin') and teacher 'mwalimu'
(password 'mwalimu') — dev only, obviously.
"""

from datetime import date, time
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.assessments.models import Assessment, LearningArea, Score
from apps.communication.models import Announcement
from apps.payments.models import FeeStructure, Invoice
from apps.schools.models import School
from django.utils import timezone

from apps.students.models import ClassGroup, Guardian, Learner, Pathway
from apps.teachers.models import SchemeOfWork, SupportStaff, Teacher, TeacherAttendance
from apps.timetable.models import LessonRequirement, Period, Room

User = get_user_model()

LEARNERS = [
    ("ADM001", "Wanjiku", "Kamau", "F", 7, 78),
    ("ADM002", "Baraka", "Otieno", "M", 7, 85),
    ("ADM003", "Amina", "Hassan", "F", 7, 55),
    ("ADM004", "Kiprop", "Cheruiyot", "M", 7, 38),
    ("ADM005", "Njeri", "Mwangi", "F", 7, 92),
]

# Name pools for the generated roster (deterministic — no randomness, so
# re-running the seed never shuffles anyone).
FIRST_MALE = [
    "Baraka", "Kiprop", "Otieno", "Mutua", "Kamau", "Odhiambo", "Kiplagat", "Njoroge",
    "Omondi", "Barasa", "Kimani", "Cheruiyot", "Wafula", "Maina", "Ochieng", "Kibet",
    "Gitonga", "Mwenda", "Onyango", "Rotich",
]
FIRST_FEMALE = [
    "Wanjiku", "Amina", "Njeri", "Achieng", "Chebet", "Wairimu", "Akinyi", "Nafula",
    "Wambui", "Jepchirchir", "Nyokabi", "Halima", "Atieno", "Chepkoech", "Muthoni",
    "Zawadi", "Nekesa", "Wangari", "Adhiambo", "Jerotich",
]
LAST_NAMES = [
    "Kamau", "Otieno", "Hassan", "Cheruiyot", "Mwangi", "Odhiambo", "Barasa", "Kiplagat",
    "Njoroge", "Omondi", "Wafula", "Maina", "Ochieng", "Kibet", "Gitonga", "Mwenda",
    "Onyango", "Rotich", "Chebet", "Nafula",
]
ALL_GRADES = [-2, -1, 0] + list(range(1, 13))  # PG, PP1, PP2, Grade 1..12
STUDENTS_PER_GRADE = 20


class Command(BaseCommand):
    help = "Seed demo data: one school, teacher, 5 learners, CAT1 scores, term fees"

    def handle(self, *args, **options):
        school, _ = School.objects.get_or_create(
            code="12345678",
            defaults={
                "name": "Demo Junior School",
                "level": School.Level.JUNIOR,
                "county": "Nairobi",
                "kemis_code": "KEMIS-12345678",
            },
        )

        for code in Pathway.Code.values:
            Pathway.objects.get_or_create(code=code)

        admin, created = User.objects.get_or_create(
            username="admin",
            defaults={"role": "ADMIN", "school": school, "is_staff": True, "is_superuser": True},
        )
        if created:
            admin.set_password("admin")
            admin.save()

        teacher_user, created = User.objects.get_or_create(
            username="mwalimu",
            defaults={"role": "TEACHER", "school": school, "first_name": "Juma", "last_name": "Mwalimu"},
        )
        if created:
            teacher_user.set_password("mwalimu")
            teacher_user.save()
        teacher, _ = Teacher.objects.get_or_create(
            user=teacher_user, defaults={"school": school, "tsc_number": "TSC123456"}
        )

        teacher2_user, created = User.objects.get_or_create(
            username="mwalimu2",
            defaults={"role": "TEACHER", "school": school, "first_name": "Achieng", "last_name": "Odhiambo"},
        )
        if created:
            teacher2_user.set_password("mwalimu2")
            teacher2_user.save()
        teacher2, _ = Teacher.objects.get_or_create(
            user=teacher2_user, defaults={"school": school, "tsc_number": "TSC654321"}
        )

        math, _ = LearningArea.objects.get_or_create(
            code="MATH", defaults={"name": "Mathematics", "grades": [7, 8, 9]}
        )
        english, _ = LearningArea.objects.get_or_create(
            code="ENG", defaults={"name": "English", "grades": [7, 8, 9]}
        )
        kiswahili, _ = LearningArea.objects.get_or_create(
            code="KIS", defaults={"name": "Kiswahili", "grades": [7, 8, 9]}
        )
        science, _ = LearningArea.objects.get_or_create(
            code="INT-SCI", defaults={"name": "Integrated Science", "grades": [7, 8, 9]}
        )

        teacher.learning_areas.add(math, science)
        teacher2.learning_areas.add(english, kiswahili)

        # Staff categories and ranks.
        Teacher.objects.filter(pk=teacher.pk).update(
            employment_type=Teacher.EmploymentType.TSC, rank=Teacher.Rank.SENIOR
        )
        Teacher.objects.filter(pk=teacher2.pk).update(
            employment_type=Teacher.EmploymentType.PNP, rank=Teacher.Rank.TEACHER
        )
        teacher3_user, created = User.objects.get_or_create(
            username="grace",
            defaults={"role": "TEACHER", "school": school,
                      "first_name": "Grace", "last_name": "Wanjala"},
        )
        if created:
            teacher3_user.set_password("grace")
            teacher3_user.save()
        Teacher.objects.get_or_create(
            user=teacher3_user,
            defaults={"school": school, "tsc_number": "BOM-2026-001",
                      "employment_type": Teacher.EmploymentType.BOM,
                      "rank": Teacher.Rank.INTERN},
        )

        SUPPORT_STAFF = [
            ("Esther Mueni", SupportStaff.Category.BURSAR, "Bursar", "BOM"),
            ("Peter Kariuki", SupportStaff.Category.SECRETARY, "School Secretary", "BOM"),
            ("Mary Adhiambo", SupportStaff.Category.KITCHEN, "Head Cook", "BOM"),
            ("Joseph Mutiso", SupportStaff.Category.KITCHEN, "Cook", "PTA"),
            ("Agnes Wafula", SupportStaff.Category.CLEANER, "Senior Cleaner", "BOM"),
            ("Daniel Kiptoo", SupportStaff.Category.CLEANER, "Cleaner", "PTA"),
            ("Samuel Njuguna", SupportStaff.Category.SECURITY, "Chief Security Officer", "CONTRACT"),
            ("Elijah Omondi", SupportStaff.Category.SECURITY, "Guard (Night)", "CONTRACT"),
            ("Beatrice Chelimo", SupportStaff.Category.NURSE, "School Nurse", "COUNTY"),
            ("Francis Ndegwa", SupportStaff.Category.DRIVER, "School Bus Driver", "BOM"),
            ("Lucy Wambua", SupportStaff.Category.GROUNDS, "Grounds Keeper", "PTA"),
        ]
        for idx, (name, category, title, employment) in enumerate(SUPPORT_STAFF, start=1):
            SupportStaff.objects.get_or_create(
                school=school, full_name=name,
                defaults={"category": category, "title": title,
                          "employment_type": employment,
                          "phone": f"25472{idx:07d}"},
            )

        # Reporting lines: the head teacher supervises staff; the head cook
        # supervises the kitchen; the bursar supervises the store keeper.
        from apps.teachers.models import Duty

        head = Teacher.objects.filter(rank=Teacher.Rank.HEAD).first()
        deputy = Teacher.objects.filter(rank=Teacher.Rank.DEPUTY).first()
        head_user = (head or teacher).user
        deputy_user = (deputy or head or teacher).user

        Teacher.objects.filter(school=school).exclude(user=head_user).update(
            supervisor=head_user
        )

        # Give every non-teaching staff member a portal login and a supervisor.
        for staff in SupportStaff.objects.filter(school=school):
            if staff.user_id is None:
                base = "".join(ch for ch in staff.full_name.split(" ")[0].lower() if ch.isalnum())
                username, n = base, 1
                while User.objects.filter(username=username).exists():
                    n += 1
                    username = f"{base}{n}"
                first, _, last = staff.full_name.partition(" ")
                account = User.objects.create_user(
                    username=username, password=username, first_name=first, last_name=last,
                    role="SUPPORT", school=school, phone=staff.phone,
                )
                staff.user = account
            staff.supervisor = deputy_user
            staff.save()

        # Kitchen reports to the head cook rather than straight to the deputy.
        head_cook = SupportStaff.objects.filter(school=school, title="Head Cook").first()
        if head_cook and head_cook.user_id:
            SupportStaff.objects.filter(
                school=school, category=SupportStaff.Category.KITCHEN
            ).exclude(pk=head_cook.pk).update(supervisor=head_cook.user)

        DUTIES = [
            (teacher.user, "Games Master", "Runs inter-class games and the sports store."),
            (teacher2.user, "Exams Coordinator", "Compiles CAT and end-term exam timetables."),
        ]
        for duty_user, title, description in DUTIES:
            Duty.objects.get_or_create(
                school=school, user=duty_user, title=title,
                defaults={"description": description},
            )

        cat1, _ = Assessment.objects.get_or_create(
            school=school, kind=Assessment.Kind.CAT1, learning_area=math,
            grade=7, stream="", term=2, year=2026, defaults={"max_marks": 100},
        )
        # CAT2 left scoreless on purpose — score-entry demo in the teacher portal.
        Assessment.objects.get_or_create(
            school=school, kind=Assessment.Kind.CAT2, learning_area=math,
            grade=7, stream="North", term=2, year=2026, defaults={"max_marks": 50},
        )
        SchemeOfWork.objects.get_or_create(
            school=school, teacher=teacher, learning_area=math, grade=7, term=2, year=2026,
            defaults={"content": {"week_1": "Integers: strands and sub-strands"}},
        )

        fees, _ = FeeStructure.objects.get_or_create(
            school=school, grade=7, term=2, year=2026,
            defaults={"amount": Decimal("15000"), "description": "Term 2 fees"},
        )

        for adm, first, last, gender, grade, marks in LEARNERS:
            learner, created = Learner.objects.get_or_create(
                school=school, admission_number=adm,
                defaults={
                    "first_name": first, "last_name": last, "gender": gender,
                    "grade": grade, "stream": "North",
                    "date_of_birth": date(2013, 5, 14), "upi": f"UPI{adm}",
                },
            )
            if created:
                guardian, _ = Guardian.objects.get_or_create(
                    school=school, phone=f"2547000000{learner.pk:02d}",
                    defaults={"full_name": f"Mzazi wa {first}", "relationship": "Parent"},
                )
                learner.guardians.add(guardian)
            Score.objects.update_or_create(
                school=school, assessment=cat1, learner=learner, defaults={"marks": marks}
            )
            Invoice.objects.get_or_create(
                school=school, learner=learner, fee_structure=fees,
                defaults={"amount_due": fees.amount},
            )

        # Parent portal login, linked to Wanjiku's guardian.
        wanjiku = Learner.objects.get(school=school, admission_number="ADM001")
        guardian = wanjiku.guardians.first()
        if guardian:
            parent_user, created = User.objects.get_or_create(
                username="mzazi",
                defaults={"role": "PARENT", "school": school,
                          "first_name": "Mzazi", "last_name": "wa Wanjiku"},
            )
            if created:
                parent_user.set_password("mzazi")
                parent_user.save()
            if guardian.user_id is None:
                guardian.user = parent_user
                guardian.save(update_fields=["user"])

        Announcement.objects.get_or_create(
            school=school,
            title="Term 2 Academic Day",
            defaults={
                "body": "Academic day on Friday. Report cards will be issued.",
                "audience": Announcement.Audience.PARENTS,
            },
        )

        # Timetable inputs: 6 periods, a lab, and G7 North weekly requirements.
        period_times = [
            (time(8, 0), time(8, 40)), (time(8, 40), time(9, 20)), (time(9, 20), time(10, 0)),
            (time(10, 30), time(11, 10)), (time(11, 10), time(11, 50)), (time(11, 50), time(12, 30)),
        ]
        for i, (start, end) in enumerate(period_times, start=1):
            Period.objects.get_or_create(
                school=school, number=i, defaults={"start_time": start, "end_time": end}
            )
        Room.objects.get_or_create(
            school=school, name="Science Lab", defaults={"is_lab": True, "capacity": 40}
        )
        # Facilities: departments with their posted staff and stores.
        from apps.facilities.models import (
            Facility,
            FacilityAssignment,
            FacilityCategory,
            Supply,
        )

        # Categories group facilities: all buses under Transport, all dorms
        # under Dormitories, and so on.
        CATEGORIES = [
            "Kitchen & Dining", "Infirmary", "Transport", "Dormitories", "Laboratories",
            "Computer Labs / ICT", "Libraries", "Sports & Games", "Farm / Agriculture",
            "Workshops", "Home Science", "Stores", "Water & Sanitation",
            "Grounds & Maintenance", "Administration", "Staff Room", "Other",
        ]
        category_by_name = {}
        for order, cname in enumerate(CATEGORIES):
            category_by_name[cname], _ = FacilityCategory.objects.get_or_create(
                school=school, name=cname, defaults={"order": order}
            )

        FACILITIES = [
            ("Main Kitchen", "Kitchen & Dining", "Behind dining hall", 400,
             [("Mary Adhiambo", "Head Cook"), ("Joseph Mutiso", "Cook")],
             [("Maize flour", "kg", 320, 100), ("Beans", "kg", 45, 60),
              ("Cooking oil", "litres", 0, 20), ("Firewood", "tonnes", 4, 2),
              ("Rice", "kg", 180, 80), ("Salt", "kg", 12, 10)]),
            ("Sick Bay", "Infirmary", "Admin block, ground floor", 6,
             [("Beatrice Chelimo", "School Nurse")],
             [("Paracetamol", "packs", 24, 10), ("Bandages", "rolls", 8, 10),
              ("ORS sachets", "pcs", 0, 25), ("Antiseptic", "litres", 3, 2),
              ("Disposable gloves", "boxes", 5, 4)]),
            ("School Bus KDJ 445K", "Transport", "Parking bay", 51,
             [("Francis Ndegwa", "Driver")],
             [("Diesel", "litres", 60, 100), ("Engine oil", "litres", 6, 4),
              ("Spare tyres", "pcs", 1, 2), ("First aid kit", "pcs", 1, 1)]),
            ("Boys Dormitory A", "Dormitories", "East wing", 120,
             [("Samuel Njuguna", "Dorm Captain (Security)")],
             [("Mattresses", "pcs", 118, 120), ("Bedsheets", "sets", 90, 100),
              ("Mosquito nets", "pcs", 0, 60), ("Buckets", "pcs", 45, 30)]),
            ("Girls Dormitory B", "Dormitories", "West wing", 120,
             [("Agnes Wafula", "Matron")],
             [("Mattresses", "pcs", 120, 120), ("Bedsheets", "sets", 105, 100),
              ("Mosquito nets", "pcs", 58, 60), ("Sanitary towels", "packs", 40, 30)]),
            ("Science Laboratory", "Laboratories", "Block C", 40,
             [("Juma Mwalimu", "Lab In-charge")],
             [("Beakers 250ml", "pcs", 30, 20), ("Bunsen burners", "pcs", 12, 10),
              ("Litmus paper", "packs", 0, 5), ("Test tubes", "pcs", 90, 50),
              ("Sodium chloride", "kg", 2, 1)]),
            ("Computer Lab", "Computer Labs / ICT", "Block D", 45,
             [("Achieng Odhiambo", "ICT Teacher In-charge")],
             [("Desktop computers", "pcs", 42, 40), ("Projectors", "pcs", 2, 1),
              ("Network cables", "pcs", 15, 10), ("Printer toner", "pcs", 0, 2)]),
            ("School Library", "Libraries", "Block A", 80,
             [("Peter Kariuki", "Librarian (acting)")],
             [("CBC course books G7", "pcs", 210, 180),
              ("Story books", "pcs", 340, 200), ("Atlases", "pcs", 25, 20)]),
            ("Sports Field & Store", "Sports & Games", "Playground", None, [],
             [("Footballs", "pcs", 6, 4), ("Netballs", "pcs", 3, 4),
              ("Volleyball nets", "pcs", 1, 1), ("First aid kit", "pcs", 0, 1)]),
            ("School Farm", "Farm / Agriculture", "North boundary", None,
             [("Lucy Wambua", "Farm Attendant")],
             [("Fertiliser (DAP)", "kg", 100, 50), ("Maize seed", "kg", 25, 20),
              ("Animal feed", "kg", 0, 40), ("Jembes", "pcs", 14, 10)]),
            ("General Stores", "Stores", "Behind admin block", None,
             [("Esther Mueni", "Store Keeper")],
             [("Exercise books", "dozens", 240, 100), ("Chalk", "boxes", 30, 20),
              ("Cleaning detergent", "litres", 18, 15), ("Toilet paper", "rolls", 0, 100)]),
            ("Water & Sanitation", "Water & Sanitation", "Whole compound", None,
             [("Daniel Kiptoo", "Sanitation Attendant")],
             [("Water treatment tablets", "packs", 12, 10),
              ("Handwash soap", "litres", 25, 20), ("Disinfectant", "litres", 0, 10)]),
        ]

        support_by_name = {s.full_name: s for s in SupportStaff.objects.filter(school=school)}
        teachers_by_name = {
            (t.user.get_full_name() or t.user.username): t
            for t in Teacher.objects.filter(school=school).select_related("user")
        }

        for name, cname, location, capacity, staff_list, supplies in FACILITIES:
            facility, _ = Facility.objects.get_or_create(
                school=school, name=name,
                defaults={"category": category_by_name[cname], "location": location,
                          "capacity": capacity},
            )
            for staff_name, position in staff_list:
                kwargs = {"school": school, "facility": facility, "position": position}
                if staff_name in teachers_by_name:
                    kwargs["teacher"] = teachers_by_name[staff_name]
                elif staff_name in support_by_name:
                    kwargs["support_staff"] = support_by_name[staff_name]
                else:
                    continue
                FacilityAssignment.objects.get_or_create(**kwargs)
            for item, unit, qty, reorder in supplies:
                Supply.objects.get_or_create(
                    school=school, facility=facility, item=item,
                    defaults={"unit": unit, "quantity": Decimal(qty),
                              "reorder_level": Decimal(reorder),
                              "last_restocked": timezone.localdate()},
                )

        # Full roster: top every grade (PP1..G12) up to 20 learners, each with a
        # guardian, a term invoice, and today's attendance mark.
        import re

        adm_numbers = Learner.objects.filter(school=school).values_list(
            "admission_number", flat=True
        )
        counter = max((int(re.sub(r"\D", "", a) or 0) for a in adm_numbers), default=0)
        today = timezone.localdate()
        generated = 0

        for grade in ALL_GRADES:
            grade_fees, _ = FeeStructure.objects.get_or_create(
                school=school, grade=grade, term=2, year=2026,
                defaults={
                    "amount": Decimal(8000 + max(grade, 0) * 500),
                    "description": f"Term 2 fees",
                },
            )
            existing = Learner.objects.filter(school=school, grade=grade, active=True).count()
            for i in range(existing, STUDENTS_PER_GRADE):
                counter += 1
                gender = "F" if i % 2 else "M"
                first = (FIRST_FEMALE if gender == "F" else FIRST_MALE)[i % 20]
                last = LAST_NAMES[(i * 7 + counter) % 20]
                adm = f"ADM{counter:03d}"
                birth_year = max(2008, 2026 - (6 + grade) - (i % 2))
                learner = Learner.objects.create(
                    school=school, admission_number=adm, upi=f"UPI{adm}",
                    first_name=first, last_name=last, gender=gender,
                    grade=grade, stream="North",
                    date_of_birth=date(birth_year, (i % 12) + 1, (i % 28) + 1),
                )
                guardian = Guardian.objects.create(
                    school=school, full_name=f"Mzazi wa {first}",
                    phone=f"25471{counter:07d}", relationship="Parent",
                )
                learner.guardians.add(guardian)
                Invoice.objects.get_or_create(
                    school=school, learner=learner, fee_structure=grade_fees,
                    defaults={"amount_due": grade_fees.amount},
                )
                generated += 1

        # Today's roll call for every learner: mostly present, a few late/absent.
        for idx, learner in enumerate(Learner.objects.filter(school=school, active=True)):
            status = "P"
            if idx % 11 == 7:
                status = "A"
            elif idx % 9 == 4:
                status = "L"
            AttendanceRecord_kwargs = {"status": status, "school": school}
            from apps.attendance.models import AttendanceRecord

            AttendanceRecord.objects.get_or_create(
                learner=learner, date=today, defaults=AttendanceRecord_kwargs
            )

        # A class group per grade; mwalimu is class teacher of G7 North.
        for grade in ALL_GRADES:
            ClassGroup.objects.get_or_create(
                school=school, grade=grade, stream="North",
                defaults={"class_teacher": teacher if grade == 7 else None},
            )
        if generated:
            self.stdout.write(f"Generated {generated} learners across {len(ALL_GRADES)} grades.")
        for tchr in (teacher, teacher2):
            TeacherAttendance.objects.get_or_create(
                school=school, teacher=tchr, date=timezone.localdate(),
                defaults={"status": TeacherAttendance.Status.PRESENT},
            )
        for tchr, area, per_week, lab in [
            (teacher, math, 5, False),
            (teacher, science, 4, True),
            (teacher2, english, 5, False),
            (teacher2, kiswahili, 4, False),
        ]:
            LessonRequirement.objects.get_or_create(
                school=school, teacher=tchr, learning_area=area, grade=7, stream="North",
                defaults={"lessons_per_week": per_week, "needs_lab": lab},
            )

        self.stdout.write(self.style.SUCCESS(
            f"Seeded {school.name}: {Learner.objects.filter(school=school).count()} learners, "
            f"CAT1 scores with competency levels, Term 2 invoices, timetable requirements. "
            "Logins: admin/admin, mwalimu/mwalimu, mzazi/mzazi (dev only)."
        ))
