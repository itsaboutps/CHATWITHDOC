from app.core.config import get_settings
from typing import BinaryIO
import uuid, pathlib, shutil, os

settings = get_settings()

BASE_DIR = pathlib.Path("data/uploads")
BASE_DIR.mkdir(parents=True, exist_ok=True)

def store_file(file_obj: BinaryIO, filename: str) -> str:
    object_name = f"{uuid.uuid4()}_{filename}"
    dest = BASE_DIR / object_name
    file_obj.seek(0)
    with open(dest, "wb") as f:
        shutil.copyfileobj(file_obj, f)
    return str(dest)

def read_file(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()

def delete_file(path: str):
    try:
        os.remove(path)
    except OSError:
        pass

def get_presigned(object_name: str, expires=3600) -> str:
    return object_name
