from __future__ import annotations

from mitra_core.pii import hash_phone, phone_last4


def test_hash_phone_is_keyed_and_deterministic() -> None:
    a = hash_phone("+919876543210", key="k1")
    assert a == hash_phone("+919876543210", key="k1")
    assert a != hash_phone("+919876543210", key="k2")
    assert a != hash_phone("+919876543211", key="k1")
    assert len(a) == 64
    assert "9876543210" not in a


def test_phone_last4() -> None:
    assert phone_last4("+919876543210") == "3210"
