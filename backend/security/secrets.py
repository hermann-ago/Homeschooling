"""Protect host-only secrets at rest.

On Windows, values are encrypted with DPAPI for the current Windows user, so a
copy of the file is useless on another account or computer. Elsewhere (tests
and development) the file is written with owner-only permissions.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_ENTROPY = b"Homeschooling home server v1"


def _dpapi(data: bytes, protect: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def blob(value: bytes) -> Blob:
        buffer = ctypes.create_string_buffer(value, len(value))
        return Blob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))

    source, entropy, result = blob(data), blob(_ENTROPY), Blob()
    crypt32 = ctypes.windll.crypt32
    function = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    CRYPTPROTECT_UI_FORBIDDEN = 0x01
    ok = function(ctypes.byref(source), None, ctypes.byref(entropy), None, None,
                  CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(result))
    if not ok:
        raise OSError("Windows could not protect or unprotect the secret")
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(result.pbData)


def write_secret(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = b"DPAPI1" + _dpapi(data, True) if sys.platform == "win32" else b"PLAIN1" + data
    temporary = path.with_suffix(".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def read_secret(path: Path) -> bytes | None:
    if not path.exists():
        return None
    payload = path.read_bytes()
    marker, body = payload[:6], payload[6:]
    if marker == b"DPAPI1":
        return _dpapi(body, False)
    if marker == b"PLAIN1":
        return body
    raise ValueError(f"Unrecognised secret file {path.name}")


def delete_secret(path: Path) -> None:
    path.unlink(missing_ok=True)
