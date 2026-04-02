from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
import os
import boto3
from uuid import uuid4
from botocore.exceptions import ClientError

AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_S3_BUCKET = os.getenv("AWS_S3_BUCKET")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

USE_S3 = all([AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_S3_BUCKET])

if USE_S3:
    s3_client = boto3.client(
        "s3",
        region_name=AWS_REGION,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    )


def save_upload(file_obj, filename, upload_dir="uploads"):
    key = f"{uuid4()}_{filename}"

    if USE_S3:
        file_obj.seek(0)
        s3_client.upload_fileobj(
            file_obj,
            AWS_S3_BUCKET,
            key,
            ExtraArgs={"ContentType": "application/octet-stream"},
        )
        return key
    else:
        os.makedirs(upload_dir, exist_ok=True)
        file_path = os.path.join(upload_dir, key)
        file_obj.seek(0)
        with open(file_path, "wb") as f:
            f.write(file_obj.read())
        return file_path


def generate_presigned_url(key, expires=3600):
    if USE_S3:
        try:
            url = s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": AWS_S3_BUCKET, "Key": key},
                ExpiresIn=expires,
            )
            return url
        except ClientError:
            return key
    return key


def get_file(key):
    """Download file from S3 into memory and return bytes, or read from local disk."""
    if USE_S3:
        response = s3_client.get_object(Bucket=AWS_S3_BUCKET, Key=key)
        return response["Body"].read()
    else:
        with open(key, "rb") as f:
            return f.read()
        def upload_file(file_obj, filename, content_type=None):
            """Alias for save_upload, compatible with main.py calls."""
            key = f"{uuid4()}_{filename}"

            if USE_S3:
                file_obj.seek(0)
                extra_args = {}
            if content_type:
                extra_args["ContentType"] = content_type
            s3_client.upload_fileobj(file_obj, AWS_S3_BUCKET, key, ExtraArgs=extra_args)
            return key
        else:
            upload_dir = PROJECT_ROOT / "uploads"
            upload_dir.mkdir(parents=True, exist_ok=True)
            file_path = upload_dir / key
            file_obj.seek(0)
            with open(file_path, "wb") as f:
            f.write(file_obj.read())
            return str(file_path)
