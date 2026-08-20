from datetime import datetime

from ninja import Schema


class DocumentResponseSchema(Schema):
    id: int
    name: str
    file_type: str
    size_bytes: int
    is_public: bool
    content_hash: str
    status: str
    error_message: str
    created_at: datetime
    updated_at: datetime


class DocumentUpdateSchema(Schema):
    is_public: bool
