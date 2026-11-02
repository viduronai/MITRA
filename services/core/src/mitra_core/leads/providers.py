"""Outbound calls to lead portals, behind interfaces with offline simulators.

* Meta Lead Ads: the leadgen webhook carries only ids; the lead itself is fetched from the Graph
  API with the page's access token. ``sim`` (default) builds a deterministic lead from the id.
* IndiaMART pull API (``crmListing/v2``): enquiries in a time window. ``sim`` returns one sample
  enquiry per window. IndiaMART's push webhook needs no provider (see ``adapters``).
* JustDial has no public pull API: it pushes to our URL only.

No real Meta or IndiaMART account is used in development or tests.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Protocol

import httpx

from mitra_core.config import Settings

GRAPH_URL = "https://graph.facebook.com/v21.0"
META_FIELDS = (
    "id,created_time,ad_id,ad_name,campaign_name,form_id,field_data,custom_disclaimer_responses"
)
INDIAMART_URL = "https://mapi.indiamart.com/wservce/crm/crmListing/v2/"
TIMEOUT = 15.0


class ProviderError(RuntimeError):
    pass


def _sim_mobile(seed: str) -> str:
    digits = str(int(hashlib.sha256(seed.encode()).hexdigest(), 16))[-8:]
    return f"+9198{digits}"


class MetaLeadsProvider(Protocol):
    async def fetch_lead(self, leadgen_id: str, access_token: str | None) -> dict[str, Any]: ...


class SimMetaLeads:
    async def fetch_lead(self, leadgen_id: str, access_token: str | None) -> dict[str, Any]:
        return {
            "id": leadgen_id,
            "campaign_name": "Simulated Meta campaign",
            "field_data": [
                {"name": "full_name", "values": ["Sim Lead"]},
                {"name": "phone_number", "values": [_sim_mobile(leadgen_id)]},
                {"name": "city", "values": ["Hyderabad"]},
            ],
        }


class GraphMetaLeads:
    async def fetch_lead(self, leadgen_id: str, access_token: str | None) -> dict[str, Any]:
        if not access_token:
            raise ProviderError("The Facebook page is not connected (no page access token)")
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                f"{GRAPH_URL}/{leadgen_id}",
                params={"access_token": access_token, "fields": META_FIELDS},
            )
        if resp.status_code != 200:
            raise ProviderError(f"Meta Graph API answered {resp.status_code}")
        data: dict[str, Any] = resp.json()
        return data


class IndiaMartProvider(Protocol):
    async def fetch(self, api_key: str, start: datetime, end: datetime) -> list[dict[str, Any]]: ...


def indiamart_time(at: datetime) -> str:
    """IndiaMART's window format: ``01-Nov-202609:00:00`` (IST)."""
    return at.strftime("%d-%b-%Y%H:%M:%S")


class SimIndiaMart:
    async def fetch(self, api_key: str, start: datetime, end: datetime) -> list[dict[str, Any]]:
        qid = f"SIM{int(start.timestamp())}"
        return [
            {
                "UNIQUE_QUERY_ID": qid,
                "QUERY_TYPE": "W",
                "SENDER_NAME": "Sim Buyer",
                "SENDER_MOBILE": "+91-" + _sim_mobile(qid)[3:],
                "SENDER_CITY": "Hyderabad",
                "QUERY_PRODUCT_NAME": "Sample product",
                "QUERY_MESSAGE": "Please share the price.",
            }
        ]


class ApiIndiaMart:
    async def fetch(self, api_key: str, start: datetime, end: datetime) -> list[dict[str, Any]]:
        params = {
            "glusr_crm_key": api_key,
            "start_time": indiamart_time(start),
            "end_time": indiamart_time(end),
        }
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(INDIAMART_URL, params=params)
        data = resp.json() if resp.status_code == 200 else {}
        if data.get("CODE") == 204:  # no enquiries in the window
            return []
        if data.get("CODE") != 200:
            raise ProviderError(f"IndiaMART answered {data.get('CODE', resp.status_code)}")
        records = data.get("RESPONSE") or []
        return [r for r in records if isinstance(r, dict)]


def get_meta_provider(settings: Settings) -> MetaLeadsProvider:
    return GraphMetaLeads() if settings.meta_leads_provider == "graph" else SimMetaLeads()


def get_indiamart_provider(settings: Settings) -> IndiaMartProvider:
    return ApiIndiaMart() if settings.indiamart_provider == "api" else SimIndiaMart()
