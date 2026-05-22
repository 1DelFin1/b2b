import io
import json
from urllib.parse import quote

from fastapi import HTTPException, status

from minio import Minio
from minio.error import S3Error

from app.core.config import settings


class MinioService:
    def __init__(self):
        self.client = Minio(
            settings.minio.MINIO_ENDPOINT,
            access_key=settings.minio.MINIO_ACCESS,
            secret_key=settings.minio.MINIO_SECRET,
            secure=settings.minio.MINIO_SECURE,
        )
        self.bucket_name = settings.minio.MINIO_BUCKET_NAME
        self.public_endpoint = settings.minio.MINIO_PUBLIC_ENDPOINT.rstrip("/")
        self._check_bucket_exists()
        self._make_bucket_public()

    def _check_bucket_exists(self):
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
        except S3Error:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Storage error",
            )

    def _make_bucket_public(self):
        try:
            policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": "*",
                        "Action": ["s3:GetObject"],
                        "Resource": [f"arn:aws:s3:::{self.bucket_name}/*"],
                    }
                ],
            }
            self.client.set_bucket_policy(self.bucket_name, json.dumps(policy))
        except S3Error:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Storage error",
            )

    def _build_public_url(self, object_name: str) -> str:
        safe_object_name = quote(object_name, safe="/")
        return f"{self.public_endpoint}/{self.bucket_name}/{safe_object_name}"

    def upload_file(self, file_data: bytes, filename: str, content_type: str) -> str:
        try:
            self.client.put_object(
                self.bucket_name,
                filename,
                io.BytesIO(file_data),
                len(file_data),
                content_type=content_type,
            )
            return self._build_public_url(filename)
        except S3Error:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Storage error",
            )

    def delete_file(self, filename: str):
        try:
            self.client.remove_object(self.bucket_name, filename)
        except S3Error:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Storage error",
            )
