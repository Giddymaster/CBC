from rest_framework import serializers

from .models import FeeStructure, Invoice, MpesaTransaction


class FeeStructureSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeeStructure
        fields = "__all__"
        read_only_fields = ["school"]


class MpesaTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = MpesaTransaction
        fields = ["id", "source", "mpesa_receipt", "phone", "amount", "account_reference", "created_at"]


class InvoiceSerializer(serializers.ModelSerializer):
    balance = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    learner_name = serializers.CharField(source="learner.full_name", read_only=True)
    transactions = MpesaTransactionSerializer(many=True, read_only=True)

    class Meta:
        model = Invoice
        fields = "__all__"
        read_only_fields = ["school", "amount_paid", "status"]


class StkPushSerializer(serializers.Serializer):
    invoice = serializers.IntegerField()
    phone = serializers.CharField(max_length=15, help_text="2547XXXXXXXX")
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
