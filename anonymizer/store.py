"""Mapping-table storage. The table is as sensitive as the original record.

Default location is outside any repository, owner-only permissions, encrypted
with Fernet (AES-128-CBC + HMAC) under a scrypt-derived key from a passphrase
(ANONYMIZER_PASSPHRASE or a prompt). --no-encrypt stores plain JSON.
"""
from __future__ import annotations

import base64
import getpass
import json
import os
from pathlib import Path

DEFAULT_DIR = Path(os.environ.get("ANONYMIZER_MAP_DIR", Path.home() / ".local/share/local-ai-anonymizer/maps"))
MAGIC = b"LAIA1"


def _key(passphrase: str, salt: bytes) -> bytes:
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    return base64.urlsafe_b64encode(Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(passphrase.encode()))


def _passphrase(confirm: bool) -> str:
    p = os.environ.get("ANONYMIZER_PASSPHRASE")
    if p:
        return p
    p = getpass.getpass("Mapping passphrase: ")
    if confirm and getpass.getpass("Repeat passphrase: ") != p:
        raise SystemExit("passphrases differ")
    return p


def save(mapping: dict, path: Path, encrypt: bool = False) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    data = json.dumps(mapping, indent=1, ensure_ascii=False).encode()
    if encrypt:
        from cryptography.fernet import Fernet
        salt = os.urandom(16)
        data = MAGIC + salt + Fernet(_key(_passphrase(True), salt)).encrypt(data)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    return path


def load(path: Path) -> dict:
    raw = Path(path).read_bytes()
    if raw.startswith(MAGIC):
        from cryptography.fernet import Fernet
        salt, tok = raw[len(MAGIC):len(MAGIC) + 16], raw[len(MAGIC) + 16:]
        raw = Fernet(_key(_passphrase(False), salt)).decrypt(tok)
    return json.loads(raw)
