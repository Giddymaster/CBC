import logging
from decimal import Decimal

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.views import SchoolScopedViewSet
from apps.schools.models import School

from .models import FeeStructure, Invoice, StkPushRequest
from .serializers import FeeStructureSerializer, InvoiceSerializer, StkPushSerializer
from .services import daraja
from .services.reconcile import record_transaction

logger = logging.getLogger(__name__)


class FeeStructureViewSet(SchoolScopedViewSet):
    queryset = FeeStructure.objects.all()
    serializer_class = FeeStructureSerializer
    filterset_fields = ["grade", "term", "year"]


class InvoiceViewSet(SchoolScopedViewSet):
    queryset = Invoice.objects.select_related("learner", "fee_structure").all()
    serializer_class = InvoiceSerializer
    # learner__grade lets the admin scope fees to one grade (e.g. ?learner__grade=5)
    filterset_fields = ["learner", "status", "fee_structure", "learner__grade"]


class StkPushView(APIView):
    """Trigger an M-Pesa STK Push for an invoice (defaults to the balance)."""

    def post(self, request):
        serializer = StkPushSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        invoice = get_object_or_404(
            Invoice.objects.filter(school=request.user.school), pk=data["invoice"]
        )
        amount = data.get("amount") or invoice.balance
        if amount <= 0:
            return Response({"detail": "Invoice is already settled."}, status=400)

        try:
            result = daraja.stk_push(
                phone=data["phone"],
                amount=int(amount),
                account_reference=invoice.learner.admission_number,
            )
        except daraja.DarajaError as exc:
            logger.error("STK push failed: %s", exc)
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        StkPushRequest.objects.create(
            school=request.user.school,
            invoice=invoice,
            phone=data["phone"],
            amount=amount,
            checkout_request_id=result.get("CheckoutRequestID"),
            merchant_request_id=result.get("MerchantRequestID", ""),
        )
        return Response(result, status=status.HTTP_202_ACCEPTED)


class StkCallbackView(APIView):
    """Daraja STK result webhook. Unauthenticated by necessity; validated by
    matching CheckoutRequestID to a request we actually made, and idempotent
    on the M-Pesa receipt number."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        callback = request.data.get("Body", {}).get("stkCallback", {})
        checkout_id = callback.get("CheckoutRequestID")
        stk_request = StkPushRequest.objects.filter(checkout_request_id=checkout_id).first()
        if not stk_request:
            logger.warning("STK callback for unknown CheckoutRequestID %s", checkout_id)
            return Response({"ResultCode": 0, "ResultDesc": "Accepted"})

        result_code = callback.get("ResultCode")
        stk_request.succeeded = result_code == 0
        stk_request.result_description = callback.get("ResultDesc", "")
        stk_request.save()

        if result_code == 0:
            items = {
                item.get("Name"): item.get("Value")
                for item in callback.get("CallbackMetadata", {}).get("Item", [])
            }
            record_transaction(
                school=stk_request.school,
                source="STK",
                receipt=items.get("MpesaReceiptNumber", f"UNKNOWN-{checkout_id}"),
                phone=str(items.get("PhoneNumber", stk_request.phone)),
                amount=items.get("Amount", stk_request.amount),
                invoice=stk_request.invoice,
                raw=callback,
            )
        return Response({"ResultCode": 0, "ResultDesc": "Accepted"})


class C2BConfirmationView(APIView):
    """Daraja C2B confirmation webhook (parent paid the paybill directly,
    account reference = admission number). Idempotent on TransID."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        data = request.data
        shortcode = str(data.get("BusinessShortCode", ""))
        school = School.objects.first() if not shortcode else (
            School.objects.filter(code=shortcode).first() or School.objects.first()
        )
        if school is None:
            return Response({"ResultCode": 0, "ResultDesc": "Accepted"})

        record_transaction(
            school=school,
            source="C2B",
            receipt=data.get("TransID", ""),
            phone=str(data.get("MSISDN", "")),
            amount=Decimal(str(data.get("TransAmount", "0"))),
            account_reference=data.get("BillRefNumber", ""),
            raw=dict(data),
        )
        return Response({"ResultCode": 0, "ResultDesc": "Accepted"})
