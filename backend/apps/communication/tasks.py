from celery import shared_task

from apps.schools.models import School

from .services import send, send_sms


@shared_task
def send_sms_task(school_id: int, recipient: str, body: str):
    school = School.objects.get(pk=school_id)
    message = send_sms(school, recipient, body)
    return message.status


@shared_task
def deliver_blast(blast_id: int):
    """Work through a blast's recipients one at a time.

    Off the request thread because a whole-school notice is nine hundred
    families and the gateway answers in its own time; the office should not sit
    on a spinner. Each parent's message is rendered from their own row, so the
    balance in a fee reminder is theirs.
    """
    from . import audience as audience_module
    from .models import MessageBlast

    blast = MessageBlast.objects.get(pk=blast_id)
    entries = audience_module.resolve(
        blast.school,
        audience=blast.audience,
        grade=blast.grade,
        stream=blast.stream,
        learner=blast.learner,
    )
    for entry in entries:
        send(
            blast.school,
            entry["phone"],
            audience_module.render(blast.body, entry, blast.school),
            channel=blast.channel,
            blast=blast,
        )
    return len(entries)


@shared_task
def blast_announcement_sms(announcement_id: int):
    """Fan an announcement out to guardian phones (Celery keeps the request fast)."""
    from apps.students.models import Guardian

    from .models import Announcement

    announcement = Announcement.objects.get(pk=announcement_id)
    phones = (
        Guardian.objects.filter(school=announcement.school)
        .exclude(phone="")
        .values_list("phone", flat=True)
        .distinct()
    )
    body = f"{announcement.title}: {announcement.body}"
    if announcement.meeting_link:
        body += f" Join: {announcement.meeting_link}"
    for phone in phones:
        send_sms(announcement.school, phone, body)
    return len(phones)
