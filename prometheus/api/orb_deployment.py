"""Fail-closed checks for Orb's single-instance public deployment."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse


def validate_public_deployment(output_root: Path, upload_root: Path, credit_db: Path) -> None:
    """Reject public startup unless paid access and durable job state are explicit."""
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
    if (parsed.scheme != "https" or not parsed.netloc or parsed.hostname in {"localhost", "127.0.0.1", "::1"}
            or origin != f"{parsed.scheme}://{parsed.netloc}"):
        raise RuntimeError("Production requires the exact HTTPS Orb frontend origin.")

    root_value = os.environ.get("ORB_DATA_DIR", "")
    root = Path(root_value)
    if not root_value or not root.is_absolute() or not root.is_dir() or not os.path.ismount(root):
        raise RuntimeError("Production requires an attached persistent disk at ORB_DATA_DIR.")
    root = root.resolve()
    if not os.environ.get("ORB_OUTPUT_DIR") or not output_root.is_relative_to(root) or output_root == root:
        raise RuntimeError("ORB_OUTPUT_DIR must be inside the attached persistent disk.")
    if not os.environ.get("ORB_CREDIT_DB") or not credit_db.is_relative_to(root):
        raise RuntimeError("ORB_CREDIT_DB must be inside the attached persistent disk.")
    upload_value = os.environ.get("ORB_UPLOAD_DIR", "")
    if not upload_value or not Path(upload_value).is_absolute() or upload_root.is_relative_to(root):
        raise RuntimeError("ORB_UPLOAD_DIR must be an absolute temporary path outside the persistent disk.")
