import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from ninja_jwt.tokens import AccessToken, RefreshToken

User = get_user_model()


class UserApiTests(TestCase):
    password = "S7rong!Passphrase"

    def setUp(self):
        self.user = User.objects.create_user(
            username="person@example.com",
            email="person@example.com",
            password=self.password,
            first_name="Old",
        )

    def authorization(self, user=None):
        token = AccessToken.for_user(user or self.user)
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def test_register_creates_user_and_profile(self):
        response = self.client.post(
            "/api/v1/user/register/",
            data=json.dumps(
                {
                    "email": "NEW@example.com",
                    "password": self.password,
                    "first_name": "New",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        created = User.objects.get(email="new@example.com")
        self.assertEqual(created.username, "new@example.com")
        self.assertTrue(created.check_password(self.password))
        self.assertEqual(created.profile.organization, None)

    def test_duplicate_registration_returns_conflict(self):
        response = self.client.post(
            "/api/v1/user/register/",
            data=json.dumps(
                {
                    "email": "PERSON@example.com",
                    "password": self.password,
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 409)

    def test_email_login_returns_token_pair(self):
        response = self.client.post(
            "/api/v1/token/pair",
            data=json.dumps({"email": self.user.email, "password": self.password}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.json())
        self.assertIn("refresh", response.json())
        refresh = RefreshToken(response.json()["refresh"])
        self.assertEqual(refresh["exp"] - refresh["iat"], 7 * 24 * 60 * 60)

    def test_profile_get_and_patch_are_separate(self):
        get_response = self.client.get("/api/v1/user/me/", **self.authorization())
        patch_response = self.client.patch(
            "/api/v1/user/me/",
            data=json.dumps({"first_name": "Updated", "organization": "Acme"}),
            content_type="application/json",
            **self.authorization(),
        )

        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(get_response.json()["first_name"], "Old")
        self.assertEqual(patch_response.status_code, 200)
        self.assertEqual(patch_response.json()["first_name"], "Updated")
        self.assertEqual(patch_response.json()["organization"], "Acme")

        clear_response = self.client.patch(
            "/api/v1/user/me/",
            data=json.dumps({"organization": None}),
            content_type="application/json",
            **self.authorization(),
        )
        self.assertEqual(clear_response.status_code, 200)
        self.assertIsNone(clear_response.json()["organization"])

    def test_profile_requires_authentication(self):
        response = self.client.get("/api/v1/user/me/")

        self.assertEqual(response.status_code, 401)

    def test_change_password_persists_the_new_password(self):
        new_password = "An0ther!StrongPass"
        response = self.client.post(
            "/api/v1/user/me/change_password/",
            data=json.dumps(
                {
                    "current_password": self.password,
                    "new_password": new_password,
                }
            ),
            content_type="application/json",
            **self.authorization(),
        )

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertFalse(self.user.check_password(self.password))
        self.assertTrue(self.user.check_password(new_password))

    def test_change_password_rejects_wrong_current_password(self):
        response = self.client.post(
            "/api/v1/user/me/change_password/",
            data=json.dumps(
                {
                    "current_password": "wrong-password",
                    "new_password": "An0ther!StrongPass",
                }
            ),
            content_type="application/json",
            **self.authorization(),
        )

        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.password))

    def test_blacklisted_refresh_token_cannot_be_reused(self):
        pair_response = self.client.post(
            "/api/v1/token/pair",
            data=json.dumps({"email": self.user.email, "password": self.password}),
            content_type="application/json",
        )
        refresh = pair_response.json()["refresh"]

        blacklist_response = self.client.post(
            "/api/v1/token/blacklist",
            data=json.dumps({"refresh": refresh}),
            content_type="application/json",
        )
        refresh_response = self.client.post(
            "/api/v1/token/refresh",
            data=json.dumps({"refresh": refresh}),
            content_type="application/json",
        )

        self.assertEqual(blacklist_response.status_code, 200)
        self.assertEqual(refresh_response.status_code, 401)

    def test_create_superuser_keeps_django_permission_flags(self):
        admin = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password=self.password,
        )

        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)
