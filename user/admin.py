from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import CustomUser, UserProfile


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("LiveDocX", {"fields": ("role",)}),)
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("LiveDocX", {"fields": ("email", "role")}),
    )
    list_display = ("email", "username", "role", "is_staff", "is_active")


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "is_verified", "updated_at")
    search_fields = ("user__email", "organization")
