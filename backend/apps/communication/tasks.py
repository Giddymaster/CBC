from celery import shared_task

from apps.schools.models import School

from .services import send_sms


@shared_task
def send_sms_task(school_id: int, recipient: str, body: str):
    school = School.objects.get(pk=school_id)
    message = send_sms(school, recipient, body)
    return message.status


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
