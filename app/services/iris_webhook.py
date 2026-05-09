"""
Encaminhador de eventos para o IRIS (dashboard real-time).

Envia POST assinado (HMAC-SHA256) para `${IRIS_WEBHOOK_URL}/api/ingest/rd` em background,
sem bloquear a resposta ao cliente original. Falhas são logadas mas não propagadas — o
fluxo principal (criar Lead no RD CRM) é mais importante que a telemetria do dashboard.
"""

import asyncio
import hashlib
import hmac
import json
import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


def _sign(body: bytes) -> str:
    if not settings.iris_webhook_secret:
        return ""
    return hmac.new(
        settings.iris_webhook_secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()


async def _post(event_type: str, payload: dict[str, Any]) -> None:
    if not settings.iris_webhook_url:
        logger.debug("[IRIS] webhook desabilitado (IRIS_WEBHOOK_URL vazio)")
        return
    body = json.dumps({"event": event_type, "payload": payload}).encode()
    headers = {
        "Content-Type": "application/json",
        "X-Iris-Event": event_type,
    }
    sig = _sign(body)
    if sig:
        headers["X-Iris-Signature"] = sig
    url = settings.iris_webhook_url.rstrip("/") + "/api/webhook/rd"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.post(url, content=body, headers=headers)
            if r.status_code >= 300:
                logger.warning(f"[IRIS] webhook retornou {r.status_code}: {r.text[:200]}")
    except Exception as e:
        logger.warning(f"[IRIS] erro ao enviar webhook event={event_type}: {e}")


def emit(event_type: str, payload: dict[str, Any]) -> None:
    """Dispara o webhook em background (sem await — fire-and-forget)."""
    asyncio.create_task(_post(event_type, payload))
