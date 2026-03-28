import os
from uuid import uuid4


def upload_file(file_obj, filename, content_type):
    upload_dir = "local_uploads"
    os.makedirs(upload_dir, exist_ok=True)

    key = f"{uuid4()}_{filename}"
    file_path = os.path.join(upload_dir, key)

    file_obj.seek(0)
    with open(file_path, "wb") as f:
        f.write(file_obj.read())

    return file_path


def generate_presigned_url(key, expires=3600):
    return key