from typing import BinaryIO

import boto3

from config.settings import settings


def client():
    return boto3.client("s3", endpoint_url=settings.minio_endpoint, aws_access_key_id=settings.minio_access_key, aws_secret_access_key=settings.minio_secret_key)


def put_object(file_id: str, body: BinaryIO, content_type: str) -> str:
    key = f"objects/{file_id}"
    client().upload_fileobj(body, settings.minio_bucket, key, ExtraArgs={"ContentType": content_type})
    return key
