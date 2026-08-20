import mimetypes

from django.conf import settings
from django.db import IntegrityError, transaction
from ninja import File, Form, Router
from ninja.errors import HttpError
from ninja.files import UploadedFile

from .models import Document
from .schemas import DocumentResponseSchema, DocumentUpdateSchema
from .utils import calculate_hash

router = Router()


def get_owned_document_or_404(user, document_id):
    try:
        return Document.objects.get(id=document_id, owner=user)
    except Document.DoesNotExist:
        raise HttpError(404, "Document not found.")


@router.post("/upload", response={201: DocumentResponseSchema})
def upload_document(
    request,
    file: File[UploadedFile],
    is_public: Form[bool] = False,
):
    if file.size == 0:
        raise HttpError(400, "The uploaded file is empty.")
    if file.size > settings.DOCUMENT_UPLOAD_MAX_SIZE:
        limit_mb = settings.DOCUMENT_UPLOAD_MAX_SIZE // (1024 * 1024)
        raise HttpError(413, f"File exceeds the {limit_mb} MB upload limit.")

    content_hash = calculate_hash(file)
    if Document.objects.filter(owner=request.auth, content_hash=content_hash).exists():
        raise HttpError(409, "You have already uploaded this file.")

    content_type = file.content_type or mimetypes.guess_type(file.name)[0]
    document = Document(
        owner=request.auth,
        name=file.name,
        file=file,
        file_type=content_type or "application/octet-stream",
        size_bytes=file.size,
        is_public=is_public,
        content_hash=content_hash,
        status=Document.Status.PENDING,
    )

    try:
        with transaction.atomic():
            document.save()
    except IntegrityError:
        # File storage is not transactional, so remove a file written by a
        # racing duplicate request when the database constraint rejects it.
        if document.file.name:
            document.file.storage.delete(document.file.name)
        raise HttpError(409, "You have already uploaded this file.")

    return 201, document


@router.get("/", response=list[DocumentResponseSchema])
def list_documents(request, include_public: bool = False):
    documents = Document.objects.filter(owner=request.auth)
    if include_public:
        documents = Document.objects.visible_to(request.auth)
    return documents


@router.get("/{document_id}", response=DocumentResponseSchema)
def get_document(request, document_id: int):
    try:
        return Document.objects.visible_to(request.auth).get(id=document_id)
    except Document.DoesNotExist:
        raise HttpError(404, "Document not found.")


@router.patch("/{document_id}", response=DocumentResponseSchema)
def update_document(request, document_id: int, payload: DocumentUpdateSchema):
    document = get_owned_document_or_404(request.auth, document_id)
    document.is_public = payload.is_public
    document.save(update_fields=("is_public", "updated_at"))
    return document


@router.delete("/{document_id}", response={204: None})
def delete_document(request, document_id: int):
    document = get_owned_document_or_404(request.auth, document_id)
    document.delete()
    return 204, None
