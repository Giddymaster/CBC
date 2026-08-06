from django.db import IntegrityError
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from .models import IdempotentRequest

IDEMPOTENCY_HEADER = "Idempotency-Key"


class IdempotencyMixin:
    """Make POST endpoints safe to retry from offline queues.

    If the request carries an Idempotency-Key header we've seen before,
    return the stored first response; otherwise process normally and store
    the outcome. Keys are client-generated (UUIDs).
    """

    def create(self, request, *args, **kwargs):
        key = request.headers.get(IDEMPOTENCY_HEADER)
        if not key:
            return super().create(request, *args, **kwargs)

        existing = IdempotentRequest.objects.filter(key=key).first()
        if existing:
            return Response(
                existing.response_body,
                status=existing.status_code,
                headers={"X-Idempotent-Replay": "true"},
            )

        response = super().create(request, *args, **kwargs)

        # Only successes are remembered. A stored 4xx/5xx would make a
        # transient failure permanent for every retry of the same key.
        if 200 <= response.status_code < 300:
            try:
                IdempotentRequest.objects.create(
                    key=key,
                    method=request.method,
                    path=request.path,
                    status_code=response.status_code,
                    response_body=response.data,
                )
            except IntegrityError:
                # Two retries raced. The other one won and stored its response;
                # ours is an equivalent duplicate, so replay theirs.
                stored = IdempotentRequest.objects.filter(key=key).first()
                if stored:
                    return Response(
                        stored.response_body,
                        status=stored.status_code,
                        headers={"X-Idempotent-Replay": "true"},
                    )
        return response


def is_admin(user):
    return user.is_superuser or getattr(user, "role", None) == "ADMIN"


def is_staff_member(user):
    return user.is_superuser or getattr(user, "role", None) in (
        "ADMIN", "TEACHER", "SUPPORT"
    )


class AdminWriteMixin:
    """Anyone signed in may read; only the school admin may write.

    The default for registry-style viewsets. Reading a room list is harmless;
    creating rooms, rewriting fee structures or publishing announcements is the
    office's job, and a viewset registered without thinking about writes should
    fail closed rather than open.
    """

    admin_write_message = "Only the school admin can change this."

    def _require_admin_write(self):
        if not is_admin(self.request.user):
            raise PermissionDenied(self.admin_write_message)

    def perform_create(self, serializer):
        self._require_admin_write()
        super().perform_create(serializer)

    def perform_update(self, serializer):
        self._require_admin_write()
        serializer.save()

    def perform_destroy(self, instance):
        self._require_admin_write()
        instance.delete()


class SchoolScopedViewSet(viewsets.ModelViewSet):
    """Base viewset enforcing row-level tenancy by the user's school."""

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_superuser:
            return qs
        if user.school_id is None:
            return qs.none()
        return qs.filter(school_id=user.school_id)

    def perform_create(self, serializer):
        user = self.request.user
        if user.school_id is not None:
            serializer.save(school=user.school)
        else:
            serializer.save()  # school-less superuser must supply school explicitly
