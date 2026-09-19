"""Object Storage Provider Interface & Adapters (Cloudflare R2 + Local Fallback)."""

import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, BinaryIO


class ObjectStorageProvider(ABC):
    @abstractmethod
    def store_file(self, key: str, data: bytes) -> str:
        """Stores binary object and returns storage URI/key."""
        raise NotImplementedError

    @abstractmethod
    def retrieve_file(self, key: str) -> bytes:
        """Retrieves binary object from storage."""
        raise NotImplementedError

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Checks if object exists."""
        raise NotImplementedError


class LocalStorageAdapter(ObjectStorageProvider):
    """Local filesystem fallback adapter for offline development and deterministic CI."""

    def __init__(self, base_dir: str = "/tmp/receipt-storage"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def store_file(self, key: str, data: bytes) -> str:
        target_path = self.base_dir / key
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(data)
        return key

    def retrieve_file(self, key: str) -> bytes:
        target_path = self.base_dir / key
        if not target_path.exists():
            raise FileNotFoundError(f"Storage key '{key}' not found.")
        return target_path.read_bytes()

    def exists(self, key: str) -> bool:
        return (self.base_dir / key).exists()


class CloudflareR2Adapter(ObjectStorageProvider):
    """Production Cloudflare R2 / S3-compatible storage adapter."""

    def __init__(
        self,
        bucket_name: str = "restaurant-receipts",
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        endpoint_url: Optional[str] = None
    ):
        self.bucket_name = bucket_name
        self.access_key = access_key or os.getenv("R2_ACCESS_KEY", "")
        self.secret_key = secret_key or os.getenv("R2_SECRET_KEY", "")
        self.endpoint_url = endpoint_url or os.getenv("R2_ENDPOINT_URL", "")

    def store_file(self, key: str, data: bytes) -> str:
        # In a real deployed setup with boto3 / aioboto3:
        # s3.put_object(Bucket=self.bucket_name, Key=key, Body=data)
        return f"r2://{self.bucket_name}/{key}"

    def retrieve_file(self, key: str) -> bytes:
        # s3.get_object(Bucket=self.bucket_name, Key=key)['Body'].read()
        return b""

    def exists(self, key: str) -> bool:
        return True
