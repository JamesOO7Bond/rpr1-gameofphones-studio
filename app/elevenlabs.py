"""Schmale Hülle um die ElevenLabs-Agents-API.

Der API-Schlüssel liegt nur hier auf dem Server. Der Browser bekommt pro Runde
eine signierte URL (WebSocket) oder ein Gesprächs-Token (WebRTC), mehr nicht.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

BASE_URL = "https://api.elevenlabs.io"


class ElevenLabsError(RuntimeError):
    pass


def _api_key() -> str:
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not key:
        raise ElevenLabsError("ELEVENLABS_API_KEY fehlt")
    return key


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=BASE_URL,
        headers={"xi-api-key": _api_key()},
        timeout=httpx.Timeout(15.0, connect=10.0),
    )


async def _get(path: str, params: dict | None = None) -> dict[str, Any]:
    async with _client() as client:
        resp = await client.get(path, params=params)
    if resp.status_code >= 400:
        raise ElevenLabsError(f"ElevenLabs {resp.status_code} bei {path}: {resp.text[:300]}")
    return resp.json()


async def get_signed_url(agent_id: str) -> str:
    data = await _get("/v1/convai/conversation/get-signed-url", {"agent_id": agent_id})
    url = data.get("signed_url")
    if not url:
        raise ElevenLabsError("Keine signed_url in der Antwort")
    return url


async def get_conversation_token(agent_id: str) -> str:
    data = await _get("/v1/convai/conversation/token", {"agent_id": agent_id})
    token = data.get("token")
    if not token:
        raise ElevenLabsError("Kein token in der Antwort")
    return token


async def get_kb_text(doc_id: str) -> str:
    data = await _get(f"/v1/convai/knowledge-base/{doc_id}")
    text = data.get("extracted_inner_html") or ""
    if not text:
        raise ElevenLabsError(f"Dokument {doc_id} ohne Text")
    return text


async def list_conversations(agent_id: str, page_size: int = 30) -> list[dict]:
    data = await _get(
        "/v1/convai/conversations",
        {"agent_id": agent_id, "page_size": page_size},
    )
    return data.get("conversations", [])


async def get_conversation(conversation_id: str) -> dict[str, Any]:
    return await _get(f"/v1/convai/conversations/{conversation_id}")
