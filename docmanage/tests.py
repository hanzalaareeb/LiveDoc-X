import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.test.utils import override_settings
from ninja_jwt.tokens import AccessToken

from .models import Document
from .utils import calculate_hash

User = get_user_model()


class DocumentApiTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.media_directory = TemporaryDirectory()
        cls.settings_override = override_settings(
            MEDIA_ROOT=cls.media_directory.name,
            DOCUMENT_UPLOAD_MAX_SIZE=1024,
        )
        cls.settings_override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.settings_override.disable()
        cls.media_directory.cleanup()

    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner@example.com",
            email="owner@example.com",
            password="S7rong!Passphrase",
        )
        self.other_user = User.objects.create_user(
            username="other@example.com",
            email="other@example.com",
            password="S7rong!Passphrase",
        )

    def authorization(self, user=None):
        token = AccessToken.for_user(user or self.owner)
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def upload(self, content=b"document content", user=None, name="notes.txt"):
        uploaded_file = SimpleUploadedFile(
            name,
            content,
            content_type="text/plain",
        )
        return self.client.post(
            "/api/v1/document/upload",
            data={"file": uploaded_file, "is_public": "false"},
            **self.authorization(user),
        )

    def test_upload_requires_authentication(self):
        response = self.client.post(
            "/api/v1/document/upload",
            data={"file": SimpleUploadedFile("notes.txt", b"content")},
        )

        self.assertEqual(response.status_code, 401)

    def test_upload_hashes_and_persists_a_private_pending_document(self):
        content = b"document content"
        response = self.upload(content=content)

        self.assertEqual(response.status_code, 201)
        document = Document.objects.get()
        self.assertEqual(document.owner, self.owner)
        self.assertEqual(document.content_hash, hashlib.sha256(content).hexdigest())
        self.assertEqual(document.size_bytes, len(content))
        self.assertEqual(document.file_type, "text/plain")
        self.assertEqual(document.status, Document.Status.PENDING)
        self.assertFalse(document.is_public)
        with document.file.open("rb") as stored_file:
            self.assertEqual(stored_file.read(), content)

    def test_duplicate_is_per_owner(self):
        first_response = self.upload()
        duplicate_response = self.upload()
        other_owner_response = self.upload(user=self.other_user)

        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(duplicate_response.status_code, 409)
        self.assertEqual(other_owner_response.status_code, 201)
        self.assertEqual(Document.objects.count(), 2)

    def test_visibility_updates_and_deletion_enforce_ownership(self):
        upload_response = self.upload()
        document_id = upload_response.json()["id"]

        private_response = self.client.get(
            f"/api/v1/document/{document_id}",
            **self.authorization(self.other_user),
        )
        forbidden_patch = self.client.patch(
            f"/api/v1/document/{document_id}",
            data=json.dumps({"is_public": True}),
            content_type="application/json",
            **self.authorization(self.other_user),
        )
        owner_patch = self.client.patch(
            f"/api/v1/document/{document_id}",
            data=json.dumps({"is_public": True}),
            content_type="application/json",
            **self.authorization(),
        )
        public_response = self.client.get(
            f"/api/v1/document/{document_id}",
            **self.authorization(self.other_user),
        )
        public_list = self.client.get(
            "/api/v1/document/?include_public=true",
            **self.authorization(self.other_user),
        )

        self.assertEqual(private_response.status_code, 404)
        self.assertEqual(forbidden_patch.status_code, 404)
        self.assertEqual(owner_patch.status_code, 200)
        self.assertEqual(public_response.status_code, 200)
        self.assertEqual([item["id"] for item in public_list.json()], [document_id])

        document = Document.objects.get(id=document_id)
        stored_path = Path(document.file.path)
        with self.captureOnCommitCallbacks(execute=True):
            delete_response = self.client.delete(
                f"/api/v1/document/{document_id}", **self.authorization()
            )

        self.assertEqual(delete_response.status_code, 204)
        self.assertFalse(Document.objects.filter(id=document_id).exists())
        self.assertFalse(stored_path.exists())

    def test_default_list_contains_only_owned_documents(self):
        own_document_id = self.upload().json()["id"]
        self.upload(content=b"other document", user=self.other_user)

        response = self.client.get("/api/v1/document/", **self.authorization())

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.json()], [own_document_id])

    def test_empty_and_oversized_uploads_are_rejected(self):
        empty_response = self.upload(content=b"")
        oversized_response = self.upload(content=b"x" * 1025)

        self.assertEqual(empty_response.status_code, 400)
        self.assertEqual(oversized_response.status_code, 413)
        self.assertEqual(Document.objects.count(), 0)

    def test_hash_utility_rewinds_the_upload(self):
        upload = SimpleUploadedFile("data.bin", b"abc")

        first_hash = calculate_hash(upload)
        second_hash = calculate_hash(upload)

        self.assertEqual(first_hash, hashlib.sha256(b"abc").hexdigest())
        self.assertEqual(second_hash, first_hash)
        self.assertEqual(upload.tell(), 0)
