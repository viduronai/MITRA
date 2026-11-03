"""Where the master key for encrypted customer numbers comes from (08-COMPLIANCE-SECURITY §6).

Exactly one source is used, checked in this order:

1. ``MITRA_PHONE_ENC_KEY_KMS``: envelope encryption. The value is the base64 KMS ciphertext of
   a 256-bit data key (make one with ``python -m mitra_core.keystore new-kms-key --key-id
   alias/mitra-staging``). It is decrypted once with AWS KMS (``kms:Decrypt`` on that key, region
   from ``MITRA_KMS_REGION``); the plaintext key lives only in this process's memory. Needs the
   ``aws`` extra (boto3).
2. ``MITRA_PHONE_ENC_KEY_FILE``: a file holding the key (a Docker / Compose secret mounted at
   ``/run/secrets/...``, readable only by the app user).
3. ``MITRA_PHONE_ENC_KEY``: the key itself in the environment (local / dev).
4. local / test only: derived from the phone-hash key.

Staging and prod refuse to start without 1, 2 or 3 (``Settings`` validation, then
:func:`check` at startup decrypts / reads it once so a bad key fails the deploy, not a call).

The key must never change once numbers are stored: every business's key is derived from it, so
a different key cannot open existing numbers. Moving the same key between sources (env -> file)
is safe; switching to a new KMS data key needs a re-seal of stored numbers first.
"""

from __future__ import annotations

import base64
import binascii
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

from mitra_core.config import Settings, get_settings

MIN_KEY_CHARS = 32


class KeyConfigError(RuntimeError):
    """The phone-encryption key is missing, unreadable or too weak."""


def _kms_client(region: str | None) -> Any:
    try:
        import boto3  # type: ignore[import-not-found]  # optional: the "aws" extra
    except ImportError as e:  # pragma: no cover - depends on the install
        raise KeyConfigError("MITRA_PHONE_ENC_KEY_KMS needs boto3 (install the 'aws' extra)") from e
    return boto3.client("kms", region_name=region)


def _from_kms(blob_b64: str, region: str | None) -> bytes:
    try:
        blob = base64.b64decode(blob_b64, validate=True)
    except (binascii.Error, ValueError) as e:
        raise KeyConfigError("MITRA_PHONE_ENC_KEY_KMS is not valid base64") from e
    try:
        plain = _kms_client(region).decrypt(CiphertextBlob=blob)["Plaintext"]
    except KeyConfigError:
        raise
    except Exception as e:  # botocore raises many types; never echo the blob
        raise KeyConfigError(f"KMS could not decrypt the phone key ({type(e).__name__})") from e
    if not isinstance(plain, bytes) or len(plain) != 32:
        raise KeyConfigError("the KMS data key must be 256 bits (KeySpec AES_256)")
    return plain


def _from_text(value: str, source: str) -> bytes:
    key = value.strip()
    if len(key) < MIN_KEY_CHARS:
        raise KeyConfigError(f"{source} must be at least {MIN_KEY_CHARS} characters")
    return key.encode()


@lru_cache(maxsize=4)
def _resolve(
    kms_blob: str | None,
    kms_region: str | None,
    key_file: str | None,
    env_key: str | None,
    fallback: str,
    strict: bool,
) -> bytes:
    if kms_blob:
        return _from_kms(kms_blob, kms_region)
    if key_file:
        try:
            text = Path(key_file).read_text(encoding="utf-8")
        except OSError as e:
            raise KeyConfigError(f"cannot read MITRA_PHONE_ENC_KEY_FILE ({e.strerror})") from e
        return _from_text(text, "MITRA_PHONE_ENC_KEY_FILE")
    if env_key:
        return _from_text(env_key, "MITRA_PHONE_ENC_KEY") if strict else env_key.encode()
    if strict:
        raise KeyConfigError(
            "set MITRA_PHONE_ENC_KEY_KMS, MITRA_PHONE_ENC_KEY_FILE or MITRA_PHONE_ENC_KEY"
        )
    return ("phone-enc:" + fallback).encode()


def phone_master_key(settings: Settings | None = None) -> bytes:
    """The master key (cached per configuration). Raises :class:`KeyConfigError`."""
    s = settings or get_settings()
    return _resolve(
        s.phone_enc_key_kms,
        s.kms_region,
        str(s.phone_enc_key_file) if s.phone_enc_key_file else None,
        s.phone_enc_key.get_secret_value() if s.phone_enc_key is not None else None,
        s.phone_hash_key.get_secret_value(),
        s.env in {"staging", "prod"},
    )


def check(settings: Settings | None = None) -> None:
    """Fail fast at startup: resolve the key once (decrypting with KMS if configured)."""
    phone_master_key(settings)


def _new_kms_key(key_id: str, region: str | None) -> str:
    """A fresh 256-bit data key from KMS, returned only in its encrypted (base64) form."""
    resp = _kms_client(region).generate_data_key_without_plaintext(KeyId=key_id, KeySpec="AES_256")
    return base64.b64encode(resp["CiphertextBlob"]).decode()


def main(argv: list[str]) -> int:
    if len(argv) >= 3 and argv[0] == "new-kms-key" and argv[1] == "--key-id":
        region = argv[argv.index("--region") + 1] if "--region" in argv else None
        print(_new_kms_key(argv[2], region))  # encrypted form only: safe to show
        return 0
    print("usage: python -m mitra_core.keystore new-kms-key --key-id <alias/...> [--region <r>]")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
