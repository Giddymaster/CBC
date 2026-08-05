"""Choosing and resetting passwords.

Until now a staff member's password was whatever the admin generated when the
account was created, shown once and never changeable. That is a credential the
admin knows, and there was no way for the person it belongs to to take it back.

Three things here:

- **Change your own** — needs the current password, so a walked-away session
  cannot lock the owner out of their own account.
- **Admin reset** — for the real case, which is a teacher who has forgotten
  theirs. Returns the new password once and marks the account as needing a
  change, so the admin's copy stops working as soon as the owner signs in.
- **Forced change** — while `must_change_password` is set the client is told to
  collect a new one before anything else.

Changing a password **invalidates the existing auth token**. A password change
is usually a response to it being known by someone else; leaving old tokens
alive would make the change cosmetic.
"""

import secrets

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

User = get_user_model()


def _rotate_token(user):
    """Old token dies; a fresh one is returned so the caller stays signed in."""
    Token.objects.filter(user=user).delete()
    return Token.objects.create(user=user).key


def _validate(password, user):
    try:
        validate_password(password, user=user)
    except DjangoValidationError as exc:
        raise serializers.ValidationError({"new_password": list(exc.messages)})


class ChangePasswordView(APIView):
    """POST /api/me/password/ — set my own password."""

    def post(self, request):
        user = request.user
        current = request.data.get("current_password") or ""
        new = request.data.get("new_password") or ""

        if not new:
            return Response(
                {"new_password": ["Choose a new password."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not user.check_password(current):
            return Response(
                {"current_password": ["That is not your current password."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if current == new:
            return Response(
                {"new_password": ["The new password must be different."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        _validate(new, user)

        user.set_password(new)
        user.must_change_password = False
        user.password_changed_at = timezone.now()
        user.save(
            update_fields=["password", "must_change_password", "password_changed_at"]
        )
        return Response(
            {
                "detail": "Password changed. Other devices will need to sign in again.",
                "token": _rotate_token(user),
            }
        )


class AdminResetPasswordView(APIView):
    """POST /api/school/staff/<user_id>/reset-password/ — admin issues a new one.

    The generated password is returned once. The account is flagged so the
    holder must replace it at next sign-in, which is what stops the admin's copy
    from remaining a working credential.
    """

    def post(self, request, user_id):
        actor = request.user
        if not (actor.is_superuser or actor.role == "ADMIN"):
            raise PermissionDenied("Only the school admin can reset a password.")

        target = User.objects.filter(pk=user_id).first()
        if target is None:
            return Response({"detail": "No such account."}, status=status.HTTP_404_NOT_FOUND)
        if not actor.is_superuser and target.school_id != actor.school_id:
            raise PermissionDenied("That account belongs to another school.")
        if target.is_superuser and not actor.is_superuser:
            raise PermissionDenied("A platform superuser's password is not yours to reset.")

        supplied = request.data.get("password")
        if supplied:
            _validate(supplied, target)
            password = supplied
        else:
            password = secrets.token_urlsafe(9)

        target.set_password(password)
        target.must_change_password = True
        target.password_changed_at = timezone.now()
        target.save(
            update_fields=["password", "must_change_password", "password_changed_at"]
        )
        # Whoever is holding the old token loses it — including the person who
        # forgot the password, which is the point.
        Token.objects.filter(user=target).delete()

        from apps.common.audit import record

        record(
            actor=actor,
            school=target.school,
            action="PASSWORD_RESET",
            target=target,
            label=target.get_full_name() or target.username,
            detail={"forced_change": True},
        )
        return Response(
            {
                "username": target.username,
                "name": target.get_full_name() or target.username,
                "generated_password": password,
                "detail": (
                    "Hand this over now — it is not shown again. They will be asked "
                    "to choose their own password when they sign in."
                ),
            }
        )
