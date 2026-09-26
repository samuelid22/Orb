"""Fail-closed checks for Orb's Postgres-backed public deployment."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

from prometheus.api.orb_database import validate_postgres_url


def validate_public_deployment(upload_root: Path, database_url: str) -> None:
    """Reject public startup unless paid access and Postgres are explicit."""
    mode = os.environ.get("ORB_ENV")
    if mode == "local":
        return
    if mode != "production":
        raise RuntimeError("Set ORB_ENV=local or ORB_ENV=production explicitly.")
    if os.environ.get("ORB_AI_LOCAL_TESTING") != "0":
        raise RuntimeError("Production requires ORB_AI_LOCAL_TESTING=0.")
    if os.environ.get("ORB_CREDITS_ENABLED") != "1":
        raise RuntimeError("Production requires ORB_CREDITS_ENABLED=1.")
    if os.environ.get("ORB_AI_PROVIDER") != "gemini" or not os.environ.get("ORB_AI_MODEL"):
        raise RuntimeError("Production requires an explicit Orb Gemini provider and model.")
    if not os.environ.get("GEMINI_API_KEY"):
        raise RuntimeError("Production requires a server-side Gemini API key.")
    if (os.environ.get("ORB_ENABLE_NIMIQ_PAYMENTS") == "1"
            or any(name.startswith("PROMETHEUS_") and value for name, value in os.environ.items())):
        raise RuntimeError("Production must use Orb-only configuration and keep inherited payments disabled.")

    origin = os.environ.get("ORB_PUBLIC_ORIGIN", "")
    parsed = urlparse(origin)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.hostname in {"localhost", "127.0.0.1", "::1"}
            or origin != f"{parsed.scheme}://{parsed.netloc}"):
        raise RuntimeError("Production requires the exact HTTPS Orb frontend origin.")

    if not database_url:
        raise RuntimeError("Production requires ORB_DATABASE_URL for the Postgres ledger and results.")
    try:
        validate_postgres_url(database_url)
    except ValueError:
        raise RuntimeError("Production requires a valid TLS Postgres ORB_DATABASE_URL.") from None

    upload_value = os.environ.get("ORB_UPLOAD_DIR", "")
    if not upload_value or not Path(upload_value).is_absolute() or not upload_root.is_absolute():
        raise RuntimeError("ORB_UPLOAD_DIR must be an absolute temporary path.")
