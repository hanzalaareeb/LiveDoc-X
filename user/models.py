from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


class CustomUser(AbstractUser):
    """Manages Core Authentication and Roles."""

    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        NORMAL = "NORMAL", "Normal"
        SYSTEM = "SYSTEM", "System"

    role = models.CharField(max_length=100, choices=Role.choices, default=Role.NORMAL)

    email = models.EmailField(unique=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    def __str__(self):
        return f"{self.username} - {self.get_role_display()}"


class UserProfile(models.Model):
    """Manages extended user data."""

    user = models.OneToOneField(
        CustomUser, on_delete=models.CASCADE, related_name="profile"
    )

    # Profile specific fields
    organization = models.CharField(max_length=255, blank=True, null=True)
    is_verified = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Profile for {self.user.email}"


@receiver(post_save, sender=CustomUser)
def ensure_user_profile(sender, instance, raw=False, **kwargs):
    """Ensure users have profiles without changing one on every user save."""
    if not raw:
        UserProfile.objects.get_or_create(user=instance)
