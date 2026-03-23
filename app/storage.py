import boto3
import os
from uuid import uuid4

s3 = boto3.client(
    "s3",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION"),
)

BUCKET = os.getenv("AWS_S3_BUCKET")

def upload_file(file_obj, filename, content_type):
    key = f"{uuid4()}_{filename}"

    s3.upload_fileobj(
        file_obj,
        BUCKET,
        key,
        ExtraArgs={"ContentType": content_type},
    )

    return key

def generate_presigned_url(key, expires=3600):
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": BUCKET, "Key": key},
        ExpiresIn=expires,
    )