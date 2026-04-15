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
    val = os.environ.get(env_name)
    if val:
        return val
    kv_name = kv_secret_name or env_name.replace("_", "-")
    return _try_keyvault(kv_name)
