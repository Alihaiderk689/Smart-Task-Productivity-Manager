import io

from django.core.files.base import ContentFile
from PIL import Image

AVATAR_MAX_SIZE = (512, 512)


def resize_avatar_file(uploaded_file):
    """Downscale an uploaded avatar to fit within AVATAR_MAX_SIZE and
    re-encode as JPEG, returning a new in-memory file ready to assign to an
    ImageField. Works regardless of storage backend (local disk, Cloudinary,
    S3, ...) since it never touches a filesystem path -- only the uploaded
    file's bytes."""

    image = Image.open(uploaded_file)
    image = image.convert("RGB")

    if image.width > AVATAR_MAX_SIZE[0] or image.height > AVATAR_MAX_SIZE[1]:
        image.thumbnail(AVATAR_MAX_SIZE)

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=90)
    buffer.seek(0)

    return ContentFile(buffer.read(), name="avatar.jpg")
