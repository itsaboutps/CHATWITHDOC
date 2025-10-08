from minio import Minio
from app.core.config import get_settings
from typing import BinaryIO
import uuid

settings = get_settings()

_client = Minio(
    settings.minio_endpoint.replace("http://", "").replace("https://", ""),
    access_key=settings.minio_root_user,
    secret_key=settings.minio_root_password,
    secure=settings.minio_endpoint.startswith("https")
)

def ensure_bucket():
    if not _client.bucket_exists(settings.minio_bucket):
        _client.make_bucket(settings.minio_bucket)


def store_file(file_obj: BinaryIO, filename: str) -> str:
    ensure_bucket()
    object_name = f"{uuid.uuid4()}_{filename}"
    file_obj.seek(0, 2)
    size = file_obj.tell()
    file_obj.seek(0)
    _client.put_object(settings.minio_bucket, object_name, file_obj, length=size)
    return object_name


def get_presigned(object_name: str, expires=3600) -> str:
    return _client.presigned_get_object(settings.minio_bucket, object_name, expires=expires)
