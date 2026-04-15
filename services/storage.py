"""
Azure Blob storage helpers — signed URLs for bill text PDFs and raw-response writes
used by the ingest clients.

Only this module touches the blob service client. Ingest code and UI code call into it.
"""

from __future__ import annotations

import gzip
import io
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from config import AZURE_STORAGE_ACCOUNT, AZURE_CONTAINER

logger = logging.getLogger(__name__)


class _StorageClient:
    def __init__(self, account_name: str, container_name: str):
        self.account_name = account_name
        self.container_name = container_name
        self._credential = None
        self._blob_service_client = None

    @property
    def credential(self):
        if self._credential is None:
            from azure.identity import DefaultAzureCredential
            self._credential = DefaultAzureCredential()
        return self._credential

    @property
    def blob_service_client(self):
        if self._blob_service_client is None:
            from azure.storage.blob import BlobServiceClient
            url = f"https://{self.account_name}.blob.core.windows.net"
            self._blob_service_client = BlobServiceClient(url, credential=self.credential)
        return self._blob_service_client

    def container_client(self):
        return self.blob_service_client.get_container_client(self.container_name)

    def upload_bytes(self, blob_name: str, data: bytes, content_type: Optional[str] = None, overwrite: bool = True):
        from azure.storage.blob import ContentSettings
        blob = self.container_client().get_blob_client(blob_name)
        blob.upload_blob(
            data,
            overwrite=overwrite,
            content_settings=ContentSettings(content_type=content_type) if content_type else None,
        )

    def upload_json_gz(self, blob_name: str, obj) -> None:
        """Used by ingest clients to write per-bill raw responses as gzipped JSON directly to blob."""
        body = gzip.compress(json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
        self.upload_bytes(blob_name, body, content_type="application/json")

    def read_json_gz(self, blob_name: str):
        blob = self.container_client().get_blob_client(blob_name)
        try:
            data = blob.download_blob().readall()
            return json.loads(gzip.decompress(data).decode("utf-8"))
        except Exception:
            return None

    def read_json(self, blob_name: str):
        blob = self.container_client().get_blob_client(blob_name)
        try:
            data = blob.download_blob().readall()
            return json.loads(data.decode("utf-8"))
        except Exception:
            return None

    def write_json(self, blob_name: str, obj) -> None:
        self.upload_bytes(blob_name, json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8"),
                          content_type="application/json")

    def signed_url(self, blob_name: str, expiry_minutes: int = 30) -> str:
        from azure.storage.blob import generate_blob_sas, BlobSasPermissions
        svc = self.blob_service_client
        delegation_key = svc.get_user_delegation_key(
            key_start_time=datetime.utcnow() - timedelta(minutes=5),
            key_expiry_time=datetime.utcnow() + timedelta(minutes=expiry_minutes + 5),
        )
        sas = generate_blob_sas(
            account_name=self.account_name,
            container_name=self.container_name,
            blob_name=blob_name,
            user_delegation_key=delegation_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.utcnow() + timedelta(minutes=expiry_minutes),
            start=datetime.utcnow() - timedelta(minutes=5),
        )
        blob_client = self.container_client().get_blob_client(blob_name)
        return f"{blob_client.url}?{sas}"


_client: Optional[_StorageClient] = None


def get_client() -> _StorageClient:
    global _client
    if _client is None:
        _client = _StorageClient(AZURE_STORAGE_ACCOUNT, AZURE_CONTAINER)
    return _client


def signed_bill_text_url(blob_path: str | None, expiry_minutes: int = 30) -> str | None:
    """Return a short-lived SAS URL for the bill text PDF. Returns None if path is empty
    or blob infrastructure isn't reachable (e.g. local dev without az login)."""
    if not blob_path:
        return None
    try:
        return get_client().signed_url(blob_path, expiry_minutes=expiry_minutes)
    except Exception as exc:
        logger.debug("signed_url failed for %s: %s", blob_path, exc)
        return None
