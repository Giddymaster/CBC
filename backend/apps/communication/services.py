"""Getting a sentence to a parent's phone.

Two carriers, one shape: SMS through Africa's Talking, WhatsApp through Meta's
Cloud API. Either way a row is written first and then updated with what the
gateway said, so an undelivered notice is a record the school can look up
rather than something that merely didn't happen.

Without credentials both store status STUBBED, so the whole flow — compose,
count, send, review — works on a laptop with no account and no spend.
"""

import logging

import requests
from django.conf import settings

from .models import Channel, SmsMessage

logger = logging.getLogger(__name__)

AT_SMS_URL = "https://api.africastalking.com/version1/messaging"
WHATSAPP_URL = "https://graph.facebook.com/v21.0/{phone_number_id}/messages"


def send(school, recipient, body, *, channel=Channel.SMS, blast=None):
    """Send on the chosen channel. The one door the rest of the app uses."""
    if channel == Channel.WHATSAPP:
        return send_whatsapp(school, recipient, body, blast=blast)
    return send_sms(school, recipient, body, blast=blast)


def send_whatsapp(school, recipient: str, body: str, *, blast=None) -> SmsMessage:
    message = SmsMessage.objects.create(
        school=school, recipient=recipient, body=body,
        channel=Channel.WHATSAPP, blast=blast,
    )

    if not (settings.WHATSAPP_TOKEN and settings.WHATSAPP_PHONE_NUMBER_ID):
        message.status = SmsMessage.Status.STUBBED
        message.save(update_fields=["status"])
        logger.info("WhatsApp (stub) to %s: %s", recipient, body)
        return message

    # Meta only allows free-form text inside a 24-hour window opened by the
    # parent. A school notice is unsolicited, so when the school has registered
    # an approved template it is used and the whole message passed as its one
    # body variable; plain text is the fallback for replies inside the window.
    if settings.WHATSAPP_TEMPLATE:
        payload = {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "template",
            "template": {
                "name": settings.WHATSAPP_TEMPLATE,
                "language": {"code": settings.WHATSAPP_TEMPLATE_LANG},
                "components": [
                    {"type": "body", "parameters": [{"type": "text", "text": body}]}
                ],
            },
        }
    else:
        payload = {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "text",
            "text": {"body": body},
        }

    try:
        response = requests.post(
            WHATSAPP_URL.format(phone_number_id=settings.WHATSAPP_PHONE_NUMBER_ID),
            headers={"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}"},
            json=payload,
            timeout=30,
        )
        data = response.json() if response.content else {}
        if response.ok and data.get("messages"):
            message.status = SmsMessage.Status.SENT
            message.provider_message_id = data["messages"][0].get("id", "")
        else:
            message.status = SmsMessage.Status.FAILED
            message.error = str(data.get("error") or data or response.status_code)
    except (requests.RequestException, ValueError) as exc:
        message.status = SmsMessage.Status.FAILED
        message.error = str(exc)

    message.save()
    return message


def send_sms(school, recipient: str, body: str, *, blast=None) -> SmsMessage:
    message = SmsMessage.objects.create(
        school=school, recipient=recipient, body=body, blast=blast
    )

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
