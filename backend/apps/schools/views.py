from rest_framework import viewsets

from apps.common.views import AdminWriteMixin

from .models import School
from .serializers import SchoolSerializer


class SchoolViewSet(AdminWriteMixin, viewsets.ModelViewSet):
    """Everyone reads their own school; only its admin edits it. The
    paybill_account_prefix on this record steers M-Pesa reconciliation, so
    an open write here would redirect how payments match invoices."""
    queryset = School.objects.all()
    serializer_class = SchoolSerializer
    search_fields = ["name", "code", "county"]

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return super().get_queryset()
        return super().get_queryset().filter(pk=user.school_id)
