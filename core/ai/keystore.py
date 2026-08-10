"""Secure API-key storage.

Primary backend is the OS keychain — Windows Credential Manager via pywin32.
Where that isn't available (non-Windows, or pywin32 missing) it falls back to
AES-256-GCM at rest, with the data key held in a 0600 sidecar file.

Rules enforced here (Phase 3):
- Keys are write-only from the app's perspective: the UI sets and masks, never
  reads a full key back for display. `masked()` is the only display path.
- `get_key()` returns the raw key ONLY to the provider layer that must auth with
  it; nothing logs it and every error message is redacted upstream.
- Legacy `.env` keys are imported once into the store; `.env` stays readable as a
  fallback so an existing install keeps working, but the store is authoritative.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path

from core.ai.registry import PROVIDERS

_SERVICE = "drift.jobs:ai"


# --------------------------------------------------------------------------- #
# Backends
# --------------------------------------------------------------------------- #
class _CredmanBackend:
    """Windows Credential Manager (generic credentials)."""

    available = False

    def __init__(self):
        try:
            import win32cred  # noqa: F401
            self.available = True
        except Exception:
            self.available = False

    def _target(self, provider: str) -> str:
        return f"{_SERVICE}:{provider}"

    def set(self, provider: str, key: str) -> None:
        import win32cred
        win32cred.CredWrite({
            "Type": win32cred.CRED_TYPE_GENERIC,
            "TargetName": self._target(provider),
            "UserName": provider,
            "CredentialBlob": key.encode("utf-8"),
            "Persist": win32cred.CRED_PERSIST_LOCAL_MACHINE,
        }, 0)

    def get(self, provider: str) -> str | None:
        import win32cred
        import pywintypes
        try:
            cred = win32cred.CredRead(self._target(provider),
                                      win32cred.CRED_TYPE_GENERIC)
        except pywintypes.error:
            return None
        blob = cred.get("CredentialBlob")
        if blob is None:
            return None
        raw = bytes(blob)
        for enc in ("utf-8", "utf-16-le"):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
        return None

    def delete(self, provider: str) -> None:
        import win32cred
        import pywintypes
        try:
            win32cred.CredDelete(self._target(provider),
                                 win32cred.CRED_TYPE_GENERIC)
        except pywintypes.error:
            pass


class _AesFileBackend:
    """AES-256-GCM at rest. Data key in a 0600 sidecar; values in a JSON file.

    Portable fallback for non-Windows and for tests. Not as strong as the OS
    keychain (a process running as the user can read the sidecar), which is why
    it is the fallback, not the default.
    """

    available = True

    def __init__(self, directory: Path):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.store_path = self.dir / "keys.enc"
        self.secret_path = self.dir / ".keyring_secret"

    def _data_key(self) -> bytes:
        if self.secret_path.is_file():
            return self.secret_path.read_bytes()
        key = os.urandom(32)
        self.secret_path.write_bytes(key)
        try:
            os.chmod(self.secret_path, 0o600)
        except OSError:
            pass
        return key

    def _load(self) -> dict:
        if not self.store_path.is_file():
            return {}
        try:
            return json.loads(self.store_path.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _save(self, data: dict) -> None:
        self.store_path.write_text(json.dumps(data), encoding="utf-8")
        try:
            os.chmod(self.store_path, 0o600)
        except OSError:
            pass

    def set(self, provider: str, key: str) -> None:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        nonce = os.urandom(12)
        ct = AESGCM(self._data_key()).encrypt(nonce, key.encode("utf-8"), None)
        data = self._load()
        data[provider] = base64.b64encode(nonce + ct).decode("ascii")
        self._save(data)

    def get(self, provider: str) -> str | None:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        blob = self._load().get(provider)
        if not blob:
            return None
        raw = base64.b64decode(blob)
        try:
            pt = AESGCM(self._data_key()).decrypt(raw[:12], raw[12:], None)
        except Exception:
            return None
        return pt.decode("utf-8")

    def delete(self, provider: str) -> None:
        data = self._load()
        if provider in data:
            del data[provider]
            self._save(data)


# --------------------------------------------------------------------------- #
# KeyStore
# --------------------------------------------------------------------------- #
def masked(key: str) -> str:
    """Display form: a hint of the prefix + last 4. Never the whole key."""
    if not key:
        return ""
    if len(key) <= 8:
        return "****"
    return f"{key[:3]}…{key[-4:]}"


class KeyStore:
    def __init__(self, fallback_dir: Path | None = None, force_file: bool = False):
        from db.connection import DB_PATH
        self._fallback_dir = fallback_dir or Path(DB_PATH).parent
        credman = _CredmanBackend()
        if force_file or not credman.available:
            self._backend = _AesFileBackend(self._fallback_dir)
        else:
            self._backend = credman
        self._legacy_imported = False

    @property
    def backend_name(self) -> str:
        return type(self._backend).__name__

    def set_key(self, provider: str, key: str) -> None:
        key = (key or "").strip()
        if not key:
            self.delete_key(provider)
            return
        self._backend.set(provider, key)

    def get_key(self, provider: str) -> str:
        """Raw key for provider auth. Import from legacy .env on first miss."""
        key = self._backend.get(provider)
        if key:
            return key
        env_val = self._legacy_env_key(provider)
        if env_val:
            # Migrate it into the store so future reads don't touch .env.
            try:
                self._backend.set(provider, env_val)
            except Exception:
                pass
            return env_val
        return ""

    def has_key(self, provider: str) -> bool:
        return bool(self.get_key(provider))

    def delete_key(self, provider: str) -> None:
        self._backend.delete(provider)

    def masked_key(self, provider: str) -> str:
        return masked(self.get_key(provider))

    def providers_with_keys(self) -> list[str]:
        return [slug for slug in PROVIDERS if self.has_key(slug)]

    # -- legacy .env ------------------------------------------------------- #
    def _legacy_env_key(self, provider: str) -> str:
        spec = PROVIDERS.get(provider)
        if not spec or not spec.env_key:
            return ""
        val = (os.environ.get(spec.env_key, "") or "").strip()
        if val.lower() in {"", "your_key_here", "changeme", "xxx"}:
            return ""
        return val


# Process-wide default store. Providers/manager use this.
_default: KeyStore | None = None


def default_store() -> KeyStore:
    global _default
    if _default is None:
        _default = KeyStore()
    return _default


def reset_default_store() -> None:
    global _default
    _default = None
