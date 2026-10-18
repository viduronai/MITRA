from __future__ import annotations

import httpx

from mitra_core.models.enums import RoleTemplate


async def test_role_templates_cover_all_roles(client: httpx.AsyncClient) -> None:
    resp = await client.get("/v1/catalog/role-templates")
    assert resp.status_code == 200
    roles = resp.json()
    assert {r["id"] for r in roles} == {r.value for r in RoleTemplate}
    receptionist = next(r for r in roles if r["id"] == "receptionist")
    assert "clinic" in receptionist["default_for"]
    assert set(receptionist) == {"id", "name", "description", "default_for", "sample_audio_url"}


async def test_voices_cover_languages_and_tiers(client: httpx.AsyncClient) -> None:
    voices = (await client.get("/v1/catalog/voices")).json()
    assert len(voices) >= 6
    assert {v["tier"] for v in voices} == {"smart", "natural", "signature"}
    for lang in ("te", "hi", "en"):
        assert any(lang in v["languages"] for v in voices), lang
    assert len({v["id"] for v in voices}) == len(voices)
    priya = next(v for v in voices if v["id"] == "priya-te-hyd")
    assert priya["dialect"] == "Hyderabadi"
    assert priya["sample_audio_url"] is None


async def test_voices_filter_by_language(client: httpx.AsyncClient) -> None:
    telugu = (await client.get("/v1/catalog/voices", params={"language": "te"})).json()
    assert telugu
    assert all("te" in v["languages"] for v in telugu)
    hindi = (await client.get("/v1/catalog/voices", params={"language": "hi"})).json()
    assert {v["id"] for v in hindi} != {v["id"] for v in telugu}
    resp = await client.get("/v1/catalog/voices", params={"language": "fr"})
    assert resp.status_code == 422


async def test_rates(client: httpx.AsyncClient) -> None:
    resp = await client.get("/v1/catalog/rates")
    assert resp.json() == [
        {"tier": "smart", "inr_per_min": 3.0},
        {"tier": "natural", "inr_per_min": 4.5},
        {"tier": "signature", "inr_per_min": 6.0},
    ]
