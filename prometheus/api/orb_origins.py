"""Exact trusted browser origins shared by CORS and signed wallet challenges."""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from starlette.middleware.cors import CORSMiddleware


_DNS_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", re.ASCII)
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
_MAX_TRUSTED_ORIGINS = 8


class OriginError(ValueError):
    """Intentionally omit configured/requested values from diagnostic messages."""


def canonical_origin(value: str) -> str:
    """Accept only HTTP(S) browser origins; HTTP is restricted to loopback."""
    if (not isinstance(value, str) or not value or len(value) > 2048
            or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value)
            or any(char in value for char in ("*", "\\", "?", "#", "@", "%", ","))):
        raise OriginError("Invalid trusted browser origin.")
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        port = parsed.port
    except ValueError:
        raise OriginError("Invalid trusted browser origin.") from None
    if (parsed.scheme not in {"http", "https"} or not host or not parsed.netloc
            or parsed.path not in {"", "/"} or parsed.netloc.endswith(":")
            or (port is not None and not 1 <= port <= 65535)):
        raise OriginError("Invalid trusted browser origin.")
    host_authority = f"[{host}]" if ":" in host else host
    if not re.fullmatch(re.escape(host_authority) + r"(?::[0-9]+)?", parsed.netloc.lower()):
        raise OriginError("Invalid trusted browser origin.")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        # Use ASCII DNS / explicit punycode, rejecting ambiguous numeric IP forms.
        labels = host.split(".")
        if (len(host) > 253 or not all(_DNS_LABEL.fullmatch(label) for label in labels)
                or labels[-1].isdigit() or re.fullmatch(r"0x[0-9a-f]+", labels[-1])):
            raise OriginError("Invalid trusted browser origin.") from None
        authority = host
    else:
        if address.version == 4 and str(address) != host:
            raise OriginError("Invalid trusted browser origin.")
        authority = f"[{address.compressed}]" if address.version == 6 else str(address)
    if parsed.scheme == "http" and host not in _LOCAL_HOSTS:
        raise OriginError("Non-local trusted origins require HTTPS.")
    if port is not None and port != {"http": 80, "https": 443}[parsed.scheme]:
        authority += f":{port}"
    return f"{parsed.scheme}://{authority}"


@dataclass(frozen=True)
class TrustedOrigins:
    primary: str
    origins: tuple[str, ...]

    @classmethod
    def parse(cls, primary: str = "", additional: str = "", *, public: bool = False) -> TrustedOrigins:
        if not isinstance(primary, str) or not isinstance(additional, str):
            raise OriginError("Trusted origins must be configured as strings.")
        primary = primary.strip()
        additional = additional.strip()
        if not primary:
            if public or additional:
                raise OriginError("ORB_PUBLIC_ORIGIN is required for trusted browser origins.")
            return cls("", ())
        values = [primary]
        if additional:
            entries = [item.strip() for item in additional.split(",")]
            if any(not item for item in entries):
                raise OriginError("ORB_ADDITIONAL_PUBLIC_ORIGINS contains an empty origin.")
            values.extend(entries)
        origins = tuple(dict.fromkeys(canonical_origin(value) for value in values))
        if len(origins) > _MAX_TRUSTED_ORIGINS:
            raise OriginError("Configure at most eight distinct trusted browser origins.")
        if public and any(urlsplit(origin).scheme != "https" or urlsplit(origin).hostname in _LOCAL_HOSTS
                          for origin in origins):
            raise OriginError("Public trusted origins require non-local HTTPS origins.")
        return cls(origins[0], origins)

    def require(self, origin: str | None) -> str:
        canonical = canonical_origin(origin)
        if canonical not in self.origins:
            raise OriginError("Browser origin is not trusted.")
        return canonical

    def challenge_origin(self, message: str) -> str:
        """Recover the signed binding without changing the existing ledger schema."""
        if not isinstance(message, str):
            raise OriginError("Invalid wallet challenge origin binding.")
        lines = message.splitlines()
        uris = [line[5:] for line in lines if line.startswith("URI: ")]
        if len(uris) != 1:
            raise OriginError("Invalid wallet challenge origin binding.")
        origin = self.require(uris[0])
        if not lines or lines[0] != f"{urlsplit(origin).netloc} wants you to sign in with your Ethereum account:":
            raise OriginError("Invalid wallet challenge origin binding.")
        return origin


class TrustedOriginCORSMiddleware(CORSMiddleware):
    """Keep Starlette's response policy, using the same canonical origin parser."""

    def is_allowed_origin(self, origin: str) -> bool:
        try:
            return super().is_allowed_origin(canonical_origin(origin))
        except OriginError:
            return False
