from __future__ import annotations
from pathlib import Path
import socket
from .config import settings

EICAR_MARKER = b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE"


def scan_file(path: Path) -> tuple[str, str]:
    data = path.read_bytes()
    if EICAR_MARKER in data:
        return "infected", "EICAR test signature detected"
    if not settings.clamav_host:
        return "not_configured", "No antivirus service configured"
    try:
        with socket.create_connection((settings.clamav_host, settings.clamav_port), timeout=10) as sock:
            sock.sendall(b"zINSTREAM\0")
            for offset in range(0, len(data), 8192):
                chunk = data[offset:offset + 8192]
                sock.sendall(len(chunk).to_bytes(4, "big") + chunk)
            sock.sendall((0).to_bytes(4, "big"))
            result = sock.recv(4096).decode("utf-8", "replace")
        if "FOUND" in result:
            return "infected", result.strip()
        if "OK" in result:
            return "clean", result.strip()
        return "error", result.strip()
    except Exception as exc:
        return "error", str(exc)
