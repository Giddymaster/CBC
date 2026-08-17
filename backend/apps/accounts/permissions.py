"""Server-side enforcement of the forced password change.

An admin-issued handover password is a credential the admin typed, read aloud
and may have written on a note. The app makes the owner replace it at first
sign-in — but if that gate lived only in the browser, anyone holding the
handover password could take the token from /api/auth/token/ and call every
endpoint directly, never visiting the change-password screen.

This closes the API side: while `must_change_password` is set, the token works
for exactly two things — seeing who you are (/api/me/) and setting a new
password (/api/me/password/). Everything else answers 403 until the password
is changed. Pair with IsAuthenticated in DEFAULT_PERMISSION_CLASSES.
"""

from rest_framework.permissions import BasePermission

# The only paths a must-change account may reach before it complies.
_ALLOWED_PREFIXES = ("/api/me",)


class PasswordChangeEnforced(BasePermission):
    message = "Set a new password before using the rest of the app."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return True  # IsAuthenticated handles the anonymous case
        if not getattr(user, "must_change_password", False):
            return True
        return request.path.startswith(_ALLOWED_PREFIXES)
