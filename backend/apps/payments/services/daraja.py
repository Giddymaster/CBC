"""Safaricom Daraja (M-Pesa) client.

Stub mode: with DARAJA_CONSUMER_KEY empty, stk_push() returns a fake
CheckoutRequestID and makes no network calls, so the full invoice -> push ->
callback -> reconciliation flow is testable locally. Point the env vars at
sandbox or production credentials to go live — the code path is identical.
"""

import base64
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from django.conf import settings

NAIROBI = ZoneInfo("Africa/Nairobi")


class DarajaError(Exception):
    pass


def _stub_mode() -> bool:
    return not settings.DARAJA_CONSUMER_KEY


def get_access_token() -> str:
    if _stub_mode():
        return "stub-token"
    credentials = base64.b64encode(
        f"{settings.DARAJA_CONSUMER_KEY}:{settings.DARAJA_CONSUMER_SECRET}".encode()
    ).decode()
    response = requests.get(
        f"{settings.DARAJA_BASE_URL}/oauth/v1/generate?grant_type=client_credentials",
        headers={"Authorization": f"Basic {credentials}"},
        timeout=30,
    )
    if response.status_code != 200:
        raise DarajaError(f"Token request failed: {response.status_code} {response.text}")
    return response.json()["access_token"]


def stk_push(phone: str, amount: int, account_reference: str, description: str = "School fees") -> dict:
    """Trigger an STK Push to the parent's phone. Returns Daraja's response
    (keys: CheckoutRequestID, MerchantRequestID, ResponseCode...)."""
    if _stub_mode():
        return {
            "CheckoutRequestID": f"ws_CO_stub_{uuid.uuid4().hex[:12]}",
            "MerchantRequestID": f"stub-{uuid.uuid4().hex[:8]}",
            "ResponseCode": "0",
            "ResponseDescription": "Stub mode: request accepted (no real push sent)",
        }

    timestamp = datetime.now(NAIROBI).strftime("%Y%m%d%H%M%S")
    password = base64.b64encode(
        f"{settings.DARAJA_SHORTCODE}{settings.DARAJA_PASSKEY}{timestamp}".encode()
    ).decode()

    response = requests.post(
        f"{settings.DARAJA_BASE_URL}/mpesa/stkpush/v1/processrequest",
        headers={"Authorization": f"Bearer {get_access_token()}"},
        json={
            "BusinessShortCode": settings.DARAJA_SHORTCODE,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": int(amount),
            "PartyA": phone,
            "PartyB": settings.DARAJA_SHORTCODE,
            "PhoneNumber": phone,
            "CallBackURL": settings.DARAJA_CALLBACK_URL,
            "AccountReference": account_reference[:12],
            "TransactionDesc": description[:13],
        },
        timeout=30,
    )
    payload = response.json()
    if response.status_code != 200 or payload.get("ResponseCode") != "0":
        raise DarajaError(f"STK push failed: {payload}")
    return payload
