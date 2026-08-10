"""Who a blast actually reaches, and what each of them is told.

Two things a school gets wrong with bulk messaging, and both cost money:

- **Duplicates.** A family with three children in the school is one phone
  number, not three. Recipients are collapsed by number.
- **Sending blind.** Every message is charged, so the count and a sample are
  worked out first and shown to the person about to press send.

Merge fields let one sentence be personal: "Dear {name}, {learner} of {class}
has a balance of KES {balance}." — one blast, the right number per family.
"""

from decimal import Decimal

from apps.schools.moe import GRADE_LABELS


def _clean_phone(raw):
    """Kenyan numbers as the gateway wants them: 2547XXXXXXXX."""
    digits = "".join(ch for ch in (raw or "") if ch.isdigit())
    if not digits:
        return ""
    if digits.startswith("0"):
        digits = "254" + digits[1:]
    elif digits.startswith(("7", "1")):
        digits = "254" + digits
    return digits if len(digits) >= 12 else ""


def resolve(school, *, audience, grade=None, stream=None, learner=None):
    """The families a blast goes to, one entry per phone number.

    Each entry carries the merge values for its own message; where a family
    has several children the first is named and the balances are summed, so
    one number gets one honest total rather than three separate demands.
    """
    from apps.payments.models import Invoice
    from apps.students.models import Learner

    learners = Learner.objects.filter(school=school, active=True).prefetch_related(
        "guardians"
    )
    if audience == "GRADE":
        if grade is None:
            return []
        learners = learners.filter(grade=grade)
        if stream:
            learners = learners.filter(stream=stream)
    elif audience == "LEARNER":
        if learner is None:
            return []
        learners = learners.filter(pk=getattr(learner, "pk", learner))

    learners = list(learners)
    balances = {}
    for invoice in Invoice.objects.filter(learner__in=learners):
        balances[invoice.learner_id] = (
            balances.get(invoice.learner_id, Decimal("0")) + invoice.balance
        )

    if audience == "UNPAID":
        learners = [
            child for child in learners if balances.get(child.id, Decimal("0")) > 0
        ]

    by_phone = {}
    for child in learners:
        for guardian in child.guardians.all():
            phone = _clean_phone(guardian.phone)
            if not phone:
                continue
            entry = by_phone.setdefault(phone, {
                "phone": phone,
                "name": guardian.full_name,
                "learner": child.full_name,
                "class": f"{GRADE_LABELS.get(child.grade, child.grade)}"
                         f"{(' ' + child.stream) if child.stream else ''}",
                "balance": Decimal("0"),
                "children": [],
            })
            entry["children"].append(child.full_name)
            entry["balance"] += balances.get(child.id, Decimal("0"))
    return sorted(by_phone.values(), key=lambda e: e["name"])


def render(body, entry, school):
    """Fill the merge fields for one family. An unknown field is left alone
    rather than blanked, so a typo shows itself instead of vanishing."""
    values = {
        "name": entry["name"],
        "learner": entry["learner"],
        "class": entry["class"],
        "balance": f"{entry['balance']:,.0f}",
        "school": school.name,
    }
    text = body
    for key, value in values.items():
        text = text.replace("{" + key + "}", str(value))
    return text
