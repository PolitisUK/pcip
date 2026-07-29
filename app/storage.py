from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import BinaryIO, Protocol
import secrets
import tempfile

from .config import settings


@dataclass
class StoredObject:
    key: str
    size: int
    sha256_hex: str
    provider: str
    uri: str = ""


class StorageBackend(Protocol):
    provider_name: str

    def ensure_ready(self) -> None: ...
    def save_stream(self, stream: BinaryIO, original_name: str, max_bytes: int) -> StoredObject: ...
    def delete(self, key: str) -> None: ...
    def scan_result(self, key: str) -> tuple[str, str]: ...
    def download_url(self, key: str, filename: str, content_type: str, minutes: int = 5) -> str | None: ...


class LocalStorage:
    provider_name = "local"

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def ensure_ready(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def save_stream(self, stream: BinaryIO, original_name: str, max_bytes: int) -> StoredObject:
        suffix = Path(original_name).suffix.lower()[:12]
        key = f"{secrets.token_hex(20)}{suffix}"
        destination = self.root / key
        digest = sha256()
        size = 0
        try:
            with destination.open("wb") as output:
                while True:
                    chunk = stream.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > max_bytes:
                        raise ValueError("File exceeds the configured upload limit.")
                    digest.update(chunk)
                    output.write(chunk)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        return StoredObject(key=key, size=size, sha256_hex=digest.hexdigest(), provider=self.provider_name)

    def path(self, key: str) -> Path:
        candidate = (self.root / key).resolve()
        if self.root.resolve() not in candidate.parents:
            raise ValueError("Invalid storage key")
        return candidate

    def delete(self, key: str) -> None:
        self.path(key).unlink(missing_ok=True)

    def scan_result(self, key: str) -> tuple[str, str]:
        return "local", "Local storage uses the configured application malware scanner."

    def download_url(self, key: str, filename: str, content_type: str, minutes: int = 5) -> str | None:
        return None


class AzureBlobStorage:
    provider_name = "azure_blob"

    def __init__(self):
        try:
            from azure.identity import DefaultAzureCredential
            from azure.storage.blob import BlobServiceClient
        except ImportError as exc:
            raise RuntimeError("Azure storage packages are not installed.") from exc

        if settings.azure_storage_connection_string:
            self.service = BlobServiceClient.from_connection_string(settings.azure_storage_connection_string)
        elif settings.azure_storage_account_url:
            self.service = BlobServiceClient(
                account_url=settings.azure_storage_account_url,
                credential=DefaultAzureCredential(exclude_interactive_browser_credential=True),
            )
        else:
            raise RuntimeError("AZURE_STORAGE_ACCOUNT_URL or AZURE_STORAGE_CONNECTION_STRING is required.")
        self.container_name = settings.azure_storage_container
        self.container = self.service.get_container_client(self.container_name)

    def ensure_ready(self) -> None:
        from azure.core.exceptions import ResourceExistsError

        try:
            self.container.create_container()
        except ResourceExistsError:
            pass

    def save_stream(self, stream: BinaryIO, original_name: str, max_bytes: int) -> StoredObject:
        suffix = Path(original_name).suffix.lower()[:12]
        key = f"evidence/{datetime.now(timezone.utc):%Y/%m/%d}/{secrets.token_hex(20)}{suffix}"
        digest = sha256()
        size = 0
        with tempfile.SpooledTemporaryFile(max_size=min(max_bytes, 8 * 1024 * 1024)) as tmp:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise ValueError("File exceeds the configured upload limit.")
                digest.update(chunk)
                tmp.write(chunk)
            tmp.seek(0)
            blob = self.container.get_blob_client(key)
            blob.upload_blob(
                tmp,
                overwrite=False,
                metadata={"pcip_sha256": digest.hexdigest(), "pcip_original_name": original_name[:256]},
            )
        return StoredObject(
            key=key,
            size=size,
            sha256_hex=digest.hexdigest(),
            provider=self.provider_name,
            uri=blob.url,
        )

    def delete(self, key: str) -> None:
        self.container.delete_blob(key, delete_snapshots="include")

    def scan_result(self, key: str) -> tuple[str, str]:
        blob = self.container.get_blob_client(key)
        try:
            tags = blob.get_blob_tags() or {}
        except Exception as exc:
            return "pending", f"Defender scan result is not yet available: {exc.__class__.__name__}."
        normalised = {str(k).strip().lower(): str(v).strip() for k, v in tags.items()}
        raw = normalised.get("malware scanning scan result") or normalised.get("malware_scan_result")
        detail = normalised.get("malware scanning scan result details", "")
        if not raw:
            return "pending", "Awaiting Microsoft Defender for Storage scan result."
        value = raw.lower()
        if value == "no threats found":
            return "clean", detail or raw
        if value == "malicious":
            return "infected", detail or raw
        if value in {"not scanned", "error"}:
            return "scan_failed", detail or raw
        return "pending", detail or raw

    def download_url(self, key: str, filename: str, content_type: str, minutes: int = 5) -> str:
        from azure.storage.blob import BlobSasPermissions, generate_blob_sas

        start = datetime.now(timezone.utc) - timedelta(minutes=1)
        expiry = datetime.now(timezone.utc) + timedelta(minutes=minutes)
        delegation_key = self.service.get_user_delegation_key(start, expiry)
        sas = generate_blob_sas(
            account_name=self.service.account_name,
            container_name=self.container_name,
            blob_name=key,
            user_delegation_key=delegation_key,
            permission=BlobSasPermissions(read=True),
            start=start,
            expiry=expiry,
            content_disposition=f'attachment; filename="{filename.replace(chr(34), "")}"',
            content_type=content_type,
        )
        blob_url = self.container.get_blob_client(key).url
        return f"{blob_url}?{sas}"


def build_storage() -> StorageBackend:
    backend = settings.storage_backend.strip().lower()
    if backend == "azure_blob":
        return AzureBlobStorage()
    if backend != "local":
        raise RuntimeError(f"Unsupported STORAGE_BACKEND: {settings.storage_backend}")
    return LocalStorage(Path(settings.local_storage_path))


storage = build_storage()
