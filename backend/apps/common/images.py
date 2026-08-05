"""Shrink uploaded photos before storing them.

A phone camera produces 3–8 MB per shot. Three hundred learners and forty staff
would put well over a gigabyte on disk for pictures displayed at 96 pixels, and
every one of them would be downloaded in full on a school's connection.

Profile photos are square-cropped from the centre — every place they appear is a
circle, so cropping here means the browser is never asked to letterbox a
portrait into a round frame.

Pillow is already required for ImageField. If it is somehow unavailable the
original file is stored untouched rather than the upload failing: a large photo
is a smaller problem than a blocked admission.
"""

import io

from django.core.files.uploadedfile import InMemoryUploadedFile

MAX_EDGE = 512          # plenty for a 96px circle on a high-density screen
JPEG_QUALITY = 82


def downscale_photo(uploaded, *, max_edge=MAX_EDGE, square=True):
    """Return a smaller version of `uploaded`, or the original if it can't be.

    The guard is on *dimensions*, not file size. A flat 2400x1600 PNG can be a
    few kilobytes on disk and is still nearly four megapixels for the browser to
    decode, and still the wrong shape for a circular frame.
    """
    if uploaded is None:
        return None

    try:
        from PIL import Image, ImageOps
    except ImportError:
        return uploaded

    try:
        uploaded.seek(0)
        image = Image.open(uploaded)
        # Phones record orientation in EXIF rather than rotating the pixels.
        image = ImageOps.exif_transpose(image)

        already_small = max(image.size) <= max_edge
        already_square = image.width == image.height
        if already_small and (already_square or not square):
            uploaded.seek(0)
            return uploaded

        if square:
            edge = min(image.size)
            left = (image.width - edge) // 2
            top = (image.height - edge) // 2
            image = image.crop((left, top, left + edge, top + edge))

        image.thumbnail((max_edge, max_edge), Image.LANCZOS)

        # Flatten transparency onto white; JPEG has no alpha channel.
        if image.mode in ("RGBA", "LA", "P"):
            image = image.convert("RGBA")
            backdrop = Image.new("RGB", image.size, (255, 255, 255))
            backdrop.paste(image, mask=image.split()[-1])
            image = backdrop
        elif image.mode != "RGB":
            image = image.convert("RGB")

        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True)
        buffer.seek(0)
    except Exception:
        # A file Pillow cannot read is one the ImageField will reject anyway,
        # with a better message than anything we could raise here.
        uploaded.seek(0)
        return uploaded

    name = getattr(uploaded, "name", "photo")
    stem = name.rsplit(".", 1)[0] or "photo"
    return InMemoryUploadedFile(
        buffer,
        field_name=getattr(uploaded, "field_name", "photo"),
        name=f"{stem}.jpg",
        content_type="image/jpeg",
        size=buffer.getbuffer().nbytes,
        charset=None,
    )
