from rest_framework import serializers

from .models import FeeStructure, Invoice, MpesaTransaction, Payment


class FeeStructureSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeeStructure
        fields = "__all__"
        read_only_fields = ["school"]


class MpesaTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = MpesaTransaction
        fields = ["id", "source", "mpesa_receipt", "phone", "amount", "account_reference", "created_at"]


class PaymentSerializer(serializers.ModelSerializer):
    method_label = serializers.CharField(source="get_method_display", read_only=True)
    received_by_name = serializers.CharField(
        source="received_by.get_full_name", read_only=True, default=None
    )

    class Meta:
        model = Payment
        fields = "__all__"
        read_only_fields = ["school", "received_by"]


class InvoiceSerializer(serializers.ModelSerializer):
    balance = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    learner_name = serializers.CharField(source="learner.full_name", read_only=True)
    # The office reads a fee register by admission number and class, not by
    # learner id — carry them so the table needs no second request.
    admission_number = serializers.CharField(
        source="learner.admission_number", read_only=True
    )
    upi = serializers.CharField(source="learner.upi", read_only=True)
    grade = serializers.IntegerField(source="learner.grade", read_only=True)
    stream = serializers.CharField(source="learner.stream", read_only=True)
    term = serializers.IntegerField(source="fee_structure.term", read_only=True)
    year = serializers.IntegerField(source="fee_structure.year", read_only=True)
    transactions = MpesaTransactionSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)

    class Meta:
        model = Invoice
        fields = "__all__"
        read_only_fields = ["school", "amount_paid", "status"]


class StkPushSerializer(serializers.Serializer):
    invoice = serializers.IntegerField()
    phone = serializers.CharField(max_length=15, help_text="2547XXXXXXXX")
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
