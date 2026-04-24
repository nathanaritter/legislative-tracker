"""
Key Vault secret lookup with env-var fallback.
Mirrors etl-base's get_api_key() pattern so secrets come from the same place across repos.
"""

from __future__ import annotations

import os
import logging
from typing import Optional

from config import KEY_VAULT_NAME

logger = logging.getLogger(__name__)


def _try_keyvault(secret_name: str) -> Optional[str]:
    try:
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient
        vault_url = f"https://{KEY_VAULT_NAME}.vault.azure.net"
        client = SecretClient(vault_url=vault_url, credential=DefaultAzureCredential())
        return client.get_secret(secret_name).value
    except Exception as exc:
        logger.debug("Key Vault lookup failed for %s: %s", secret_name, exc)
        return None


def get_secret(env_name: str, kv_secret_name: Optional[str] = None) -> Optional[str]:
    """Look up a secret: env var first, then Key Vault. Returns None if not found."""
    # Mirror etl-base/etl/shared/get_api_key pattern — auto-load .env so scripts
    # run from a sibling repo's cwd still see the shared keys. Search both repos
    # explicitly (cwd + sibling etl-base) so running from either works.
    try:
        from dotenv import load_dotenv
        import pathlib
        here = pathlib.Path(__file__).resolve()
        # This file: <repo>/ingest/keyvault.py — walk up to find .env in the
        # legislative-tracker repo, and also try ../etl-base/.env.
        candidates = [
            here.parent.parent / ".env",                        # legislative-tracker/.env
            here.parent.parent.parent / "etl-base" / ".env",    # sibling etl-base/.env
            pathlib.Path.cwd() / ".env",                        # current working dir
        ]
        for p in candidates:
            if p.exists():
                load_dotenv(p, override=False)
    except ImportError:
        pass

    val = os.environ.get(env_name)
    if val:
        return val
    kv_name = kv_secret_name or env_name.replace("_", "-")
    return _try_keyvault(kv_name)
