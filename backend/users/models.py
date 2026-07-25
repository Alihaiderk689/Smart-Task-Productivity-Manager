from django.conf import settings
from django.db import models

AVATAR_MAX_SIZE = (512, 512)


class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    avatar = models.ImageField(upload_to="avatars/", null=True, blank=True)

    def __str__(self):
        return f"{self.user.email}'s profile"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        if not self.avatar:
            return

        from PIL import Image

        image = Image.open(self.avatar.path)
        if image.width > AVATAR_MAX_SIZE[0] or image.height > AVATAR_MAX_SIZE[1]:
            image.thumbnail(AVATAR_MAX_SIZE)
            image.save(self.avatar.path)
