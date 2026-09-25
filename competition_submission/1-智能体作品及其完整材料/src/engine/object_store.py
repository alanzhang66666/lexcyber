from __future__ import annotations

from pathlib import Path

import boto3
from botocore.client import Config

from engine.settings import settings


def fetch_object_bytes(storage_key: str) -> bytes:
    if settings.object_storage_provider == "filesystem":
        root = Path(settings.object_storage_root).resolve()
        target = (root / storage_key).resolve()
        if not target.is_relative_to(root):
            raise RuntimeError("invalid object storage key")
        return target.read_bytes()
    if not settings.minio_endpoint or not settings.minio_access_key or not settings.minio_secret_key:
        raise RuntimeError("object storage is not configured")
    client = boto3.client(
        "s3",
        endpoint_url=settings.minio_endpoint,
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        region_name="us-east-1",
    )
    response = client.get_object(Bucket=settings.minio_bucket, Key=storage_key)
    return response["Body"].read()
