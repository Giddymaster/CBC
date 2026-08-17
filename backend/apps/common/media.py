"""Uploaded files behind signed links.

A school's uploads are its private papers: learner photos, the head teacher's
filed board minutes, a teacher's scheme of work. They used to be served
straight off the media volume, which meant any visitor who guessed
/media/learner_photos/... could read them — no login asked.

Now every URL the API hands out carries a signature over the file's path with
an expiry. The media endpoint checks the signature before streaming a byte and
answers 403 otherwise. A link is a time-limited ticket to one file, not a map
of the archive: it cannot be minted by a visitor, altered to fetch a different
file, or hoarded past its expiry.

Kept as plain Django (no DRF auth) on purpose — the browser fetches these via
<img src> and plain anchor tags, which carry no Authorization header. The
signature IS the credential.
"""

from django.conf import settings
from django.core import signing
from django.http import FileResponse, HttpResponseForbidden, HttpResponseNotFound
from django.utils._os import safe_join
from rest_framework import serializers

SALT = "school-media"
MAX_AGE_SECONDS = 12 * 60 * 60  # long enough for a working day, not for a leak


def media_token(name: str) -> str:
    return signing.dumps(name, salt=SALT, compress=True)


def signed_media_url(request, filefield):
    """An absolute, signed, expiring URL for an uploaded file (or None)."""
    if not filefield:
        return None
    path = f"/media/{filefield.name}?t={media_token(filefield.name)}"
    return request.build_absolute_uri(path) if request is not None else path


class SignedFileField(serializers.FileField):
    """Drop-in for serializers whose model has a FileField/ImageField: the
    JSON carries the signed link instead of the naked /media path."""

    def to_representation(self, value):
        request = self.context.get("request")
        return signed_media_url(request, value)


def serve_media(request, path):
    """GET /media/<path>?t=<signature> — stream the file the ticket names.

    The signature covers the exact path, so tampering with either the path or
    the token fails verification; there is no way to walk from one valid link
    to a neighbouring file.
    """
    token = request.GET.get("t", "")
    try:
        signed_for = signing.loads(token, salt=SALT, max_age=MAX_AGE_SECONDS)
    except signing.BadSignature:
        return HttpResponseForbidden("This link is not valid or has expired.")
    if signed_for != path:
        return HttpResponseForbidden("This link is for a different file.")

    try:
        full_path = safe_join(settings.MEDIA_ROOT, path)
    except (ValueError, TypeError):
        return HttpResponseNotFound()
    try:
        return FileResponse(open(full_path, "rb"))
    except (FileNotFoundError, IsADirectoryError, PermissionError, OSError):
        return HttpResponseNotFound()
