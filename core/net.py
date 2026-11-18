from __future__ import annotations

import socket

PROBES = (("1.1.1.1", 443), ("8.8.8.8", 53))


def has_internet(timeout: float = 1.4) -> bool:
    for host, port in PROBES:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            continue
    return False
