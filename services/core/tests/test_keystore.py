"""Where the phone-encryption master key comes from (mitra_core.keystore)."""

from __future__ import annotations

import base64
import uuid
from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr, ValidationError

from mitra_core import keystore
from mitra_core.config import Settings
from mitra_core.keystore import KeyConfigError, phone_master_key

PROD: dict[str, Any] = {
    "env": "prod",
    "jwt_secret": SecretStr("s" * 40),
    "phone_hash_key": SecretStr("p" * 40),
    "otp_hash_key": SecretStr("o" * 40),
    "service_token": SecretStr("t" * 40),
    "payment_provider": "razorpay",
    "collections_provider": "razorpay",
}


@pytest.fixture(autouse=True)
def _fresh_cache() -> None:
    keystore._resolve.cache_clear()


def test_prod_refuses_to_start_without_a_phone_key() -> None:
    with pytest.raises(ValidationError, match="MITRA_PHONE_ENC_KEY_KMS"):
        Settings(**PROD)
    with pytest.raises(ValidationError, match="at least 32 characters"):
        Settings(**PROD, phone_enc_key=SecretStr("short"))


def test_local_falls_back_to_a_derived_key() -> None:
    local = Settings(env="local", phone_hash_key=SecretStr("p" * 40))
    assert phone_master_key(local) == b"phone-enc:" + b"p" * 40


def test_key_file_gives_the_same_key_as_the_env_value(tmp_path: Path) -> None:
    key = "k" * 48
    secret = tmp_path / "phone_enc_key"
    secret.write_text(key + "\n", encoding="utf-8")
    from_file = phone_master_key(Settings(**PROD, phone_enc_key_file=secret))
    from_env = phone_master_key(Settings(**PROD, phone_enc_key=SecretStr(key)))
    assert from_file == from_env == key.encode()  # moving env -> file keeps numbers readable


def test_unreadable_or_weak_key_file_fails(tmp_path: Path) -> None:
    with pytest.raises(KeyConfigError, match="cannot read"):
        phone_master_key(Settings(**PROD, phone_enc_key_file=tmp_path / "missing"))
    weak = tmp_path / "weak"
    weak.write_text("tooshort", encoding="utf-8")
    with pytest.raises(KeyConfigError, match="at least 32"):
        phone_master_key(Settings(**PROD, phone_enc_key_file=weak))


class _FakeKms:
    def __init__(self, plaintext: bytes) -> None:
        self.plaintext, self.calls = plaintext, 0

    def decrypt(self, CiphertextBlob: bytes) -> dict[str, bytes]:  # noqa: N803 (boto3 name)
        self.calls += 1
        assert CiphertextBlob == b"wrapped-key"
        return {"Plaintext": self.plaintext}


def test_kms_data_key_is_decrypted_once(monkeypatch: pytest.MonkeyPatch) -> None:
    kms = _FakeKms(bytes(range(32)))
    monkeypatch.setattr(keystore, "_kms_client", lambda region: kms)
    blob = base64.b64encode(b"wrapped-key").decode()
    settings = Settings(**PROD, phone_enc_key_kms=blob)
    assert phone_master_key(settings) == bytes(range(32))
    assert phone_master_key(settings) == bytes(range(32))
    assert kms.calls == 1


def test_kms_errors_never_leak_the_blob(monkeypatch: pytest.MonkeyPatch) -> None:
    class Denied:
        def decrypt(self, CiphertextBlob: bytes) -> dict[str, bytes]:  # noqa: N803
            raise PermissionError("AccessDenied")

    monkeypatch.setattr(keystore, "_kms_client", lambda region: Denied())
    blob = base64.b64encode(b"wrapped-key").decode()
    with pytest.raises(KeyConfigError, match=r"KMS could not decrypt the phone key \(Permission"):
        phone_master_key(Settings(**PROD, phone_enc_key_kms=blob))
    with pytest.raises(KeyConfigError, match="not valid base64"):
        phone_master_key(Settings(**PROD, phone_enc_key_kms="!!not base64!!"))
    monkeypatch.setattr(keystore, "_kms_client", lambda region: _FakeKms(b"short"))
    with pytest.raises(KeyConfigError, match="256 bits"):
        phone_master_key(Settings(**PROD, phone_enc_key_kms=blob))


def test_seal_uses_the_configured_key(monkeypatch: pytest.MonkeyPatch) -> None:
    from mitra_core import phones

    biz = uuid.uuid4()
    monkeypatch.setattr(phones, "phone_master_key", lambda: b"a" * 32)
    sealed = phones.seal_phone(biz, "+919811112222")
    assert phones.unseal_phone(biz, sealed) == "+919811112222"
    monkeypatch.setattr(phones, "phone_master_key", lambda: b"b" * 32)
    with pytest.raises(phones.PhoneSealError):
        phones.unseal_phone(biz, sealed)  # another key cannot open it
