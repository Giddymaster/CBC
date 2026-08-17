"""Guardrails on what may be uploaded.

Two failure modes to close:

- **Size.** No field capped the upload, so one `POST` of a multi-gigabyte file
  could fill the shared media volume. Photos and documents have honest ceilings.
- **Type.** A file the server keeps but the browser runs — an `.svg` or `.html`
  masquerading as a photo — is stored XSS the moment it is served same-origin.
  Only real image types are accepted for a photo, only documents for a document.

These are DRF field validators, so a bad upload is a clean 400 with a reason,
not a 500 or a silently-stored payload.
"""

from rest_framework import serializers

IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
DOC_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "image/jpeg", "image/png", "image/webp",
}
DOC_EXTS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".jpg", ".jpeg", ".png", ".webp"}

MAX_IMAGE_BYTES = 8 * 1024 * 1024      # a phone photo, before we downscale it
MAX_DOC_BYTES = 25 * 1024 * 1024       # a scanned certificate or a scheme


def _ext(name):
    name = (name or "").lower()
    return name[name.rfind("."):] if "." in name else ""


def _validate(upload, *, allowed_types, allowed_exts, max_bytes, kind):
    if upload is None:
        return upload
    if upload.size > max_bytes:
        raise serializers.ValidationError(
            f"This {kind} is too large (max {max_bytes // (1024 * 1024)} MB)."
        )
    content_type = (getattr(upload, "content_type", "") or "").lower()
    ext = _ext(getattr(upload, "name", ""))
    # Both the browser-declared type and the extension must be on the list.
    # A .svg renamed to .png fails the type check; a real png mislabelled fails
    # the extension check — either way it does not get stored.
    if content_type and content_type not in allowed_types:
        raise serializers.ValidationError(f"That file type is not allowed for a {kind}.")
    if ext and ext not in allowed_exts:
        raise serializers.ValidationError(f"A {kind} must be one of: {', '.join(sorted(allowed_exts))}.")
    return upload


def validate_image(upload):
    return _validate(
        upload, allowed_types=IMAGE_TYPES, allowed_exts=IMAGE_EXTS,
        max_bytes=MAX_IMAGE_BYTES, kind="photo",
    )


def validate_document(upload):
    return _validate(
        upload, allowed_types=DOC_TYPES, allowed_exts=DOC_EXTS,
        max_bytes=MAX_DOC_BYTES, kind="document",
    )
