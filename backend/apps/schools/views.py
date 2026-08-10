from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied

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

    def _operator_only(self):
        """Schools are enrolled and closed from the operator console, never
        from inside one. A school admin editing their own record is ordinary
        housekeeping; a school admin creating a second tenant, or deleting the
        one they are signed into, is not."""
        if not self.request.user.is_superuser:
            raise PermissionDenied("Schools are enrolled and closed by the operator.")

    def perform_create(self, serializer):
        self._operator_only()
        super().perform_create(serializer)

    def perform_destroy(self, instance):
        self._operator_only()
        super().perform_destroy(instance)
