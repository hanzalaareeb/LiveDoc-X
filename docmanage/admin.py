from django.contrib import admin

from .models import Document, DocumentChunk


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "owner",
        "status",
        "is_public",
        "size_bytes",
        "created_at",
    )
    list_filter = ("status", "is_public", "file_type")
    search_fields = ("name", "owner__email", "content_hash")
    readonly_fields = ("content_hash", "size_bytes", "created_at", "updated_at")


@admin.register(DocumentChunk)
class DocumentChunkAdmin(admin.ModelAdmin):
    list_display = ("document", "chunk_index", "page_number")
    search_fields = ("document__name", "content")
