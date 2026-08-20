from django.conf import settings
from django.db import models, transaction
from django.db.models import Q
from django.db.models.signals import post_delete
from django.dispatch import receiver
from pgvector.django import VectorField


class DocumentQuerySet(models.QuerySet):
    def visible_to(self, user):
        """Return documents the user owns or that have been made public."""
        return self.filter(Q(owner=user) | Q(is_public=True))


class Document(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="documents",
        on_delete=models.CASCADE,
    )
    name = models.CharField(max_length=255)
    file = models.FileField(upload_to="documents/")
    file_type = models.CharField(max_length=255)
    size_bytes = models.PositiveBigIntegerField(default=0)
    is_public = models.BooleanField(default=False)
    content_hash = models.CharField(max_length=64, db_index=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = DocumentQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("owner", "content_hash"),
                name="unique_document_content_per_owner",
            )
        ]
        ordering = ("-created_at",)

    def __str__(self):
        return self.name


class DocumentChunk(models.Model):
    document = models.ForeignKey(
        Document, related_name="chunks", on_delete=models.CASCADE
    )
    content = models.TextField()
    page_number = models.PositiveIntegerField()
    chunk_index = models.PositiveIntegerField(default=0)
    embedding = VectorField(dimensions=1536, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("document", "chunk_index"),
                name="unique_chunk_index_per_document",
            )
        ]
        ordering = ("document_id", "chunk_index")

    def __str__(self):
        return f"{self.document.name} — chunk {self.chunk_index}"


@receiver(post_delete, sender=Document)
def delete_document_file_after_commit(sender, instance, **kwargs):
    """Delete stored content only after its database deletion commits."""
    if not instance.file.name:
        return

    storage = instance.file.storage
    file_name = instance.file.name
    transaction.on_commit(lambda: storage.delete(file_name), robust=True)
