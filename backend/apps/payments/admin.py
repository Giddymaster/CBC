from django.contrib import admin

from .models import FeeStructure, Invoice, MpesaTransaction, StkPushRequest

admin.site.register(FeeStructure)


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("id", "learner", "amount_due", "amount_paid", "status")
    list_filter = ("status",)


@admin.register(MpesaTransaction)
class MpesaTransactionAdmin(admin.ModelAdmin):
    list_display = ("mpesa_receipt", "amount", "phone", "source", "invoice")
    list_filter = ("source",)
    search_fields = ("mpesa_receipt", "phone", "account_reference")


admin.site.register(StkPushRequest)
