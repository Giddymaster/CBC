"""SMS via Africa's Talking. Without AT_API_KEY set, messages are stored with
status STUBBED so the whole flow is testable with no account."""

import logging

import requests
from django.conf import settings

from .models import SmsMessage

logger = logging.getLogger(__name__)

AT_SMS_URL = "https://api.africastalking.com/version1/messaging"


def send_sms(school, recipient: str, body: str) -> SmsMessage:
    message = SmsMessage.objects.create(school=school, recipient=recipient, body=body)

    if not settings.AT_API_KEY:
        message.status = SmsMessage.Status.STUBBED
        message.save(update_fields=["status"])
        logger.info("SMS (stub) to %s: %s", recipient, body)
        return message

    try:
        response = requests.post(
            AT_SMS_URL,
            headers={"apiKey": settings.AT_API_KEY, "Accept": "application/json"},
            data={
                "username": settings.AT_USERNAME,
                "to": recipient,
                "message": body,
                **({"from": settings.AT_SENDER_ID} if settings.AT_SENDER_ID else {}),
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        recipients = payload.get("SMSMessageData", {}).get("Recipients", [])
        if recipients and recipients[0].get("status") == "Success":
            message.status = SmsMessage.Status.SENT
            message.provider_message_id = recipients[0].get("messageId", "")
        else:
            message.status = SmsMessage.Status.FAILED
            message.error = str(payload)
    except requests.RequestException as exc:
        message.status = SmsMessage.Status.FAILED
        message.error = str(exc)

    message.save()
    return message
