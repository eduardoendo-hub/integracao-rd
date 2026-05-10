"""
Meta Conversions API (CAPI) — envia eventos server-side para o Pixel Meta.

Por que server-side: iOS 14+ e browsers com anti-tracking (Brave, Firefox)
bloqueiam ~30-50% dos eventos do Pixel client-side. Enviar pelo servidor
garante a entrega.

Deduplicação com client-side: usar o MESMO `event_id` (UUID) gerado no
client e enviado em ambos os lados. Meta deduplica automaticamente quando
recebe os 2 com mesmo event_id em até ~24h.

Doc: https://developers.facebook.com/docs/marketing-api/conversions-api
"""

import hashlib
import logging
import time
from typing import Any, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_GRAPH = "https://graph.facebook.com/v19.0"


def _sha256(s: Optional[str]) -> Optional[str]:
    """Hash SHA256 lowercase trimmed — formato exigido pelo Meta."""
    if not s:
        return None
    s = s.strip().lower()
    if not s:
        return None
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _normalize_phone_for_capi(phone: Optional[str]) -> Optional[str]:
    """Meta espera phone só com dígitos, com country code, sem '+' nem espaços."""
    if not phone:
        return None
    digits = "".join(c for c in phone if c.isdigit())
    if not digits:
        return None
    # Adiciona DDI Brasil se faltar (heurística)
    if len(digits) in (10, 11) and not digits.startswith("55"):
        digits = "55" + digits
    return digits


async def send_event(
    *,
    event_name: str,
    event_id: str,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    first_name: Optional[str] = None,
    event_source_url: Optional[str] = None,
    client_ip: Optional[str] = None,
    client_user_agent: Optional[str] = None,
    fbc: Optional[str] = None,
    fbp: Optional[str] = None,
    value: Optional[float] = None,
    currency: str = "BRL",
    extra_custom_data: Optional[dict[str, Any]] = None,
) -> bool:
    """Envia evento ao Meta CAPI. Retorna True se aceito (200/201)."""
    if not settings.meta_pixel_id or not settings.meta_capi_token:
        logger.debug("[Meta CAPI] credenciais ausentes — evento ignorado")
        return False

    user_data: dict[str, Any] = {}
    em = _sha256(email)
    if em:
        user_data["em"] = [em]
    norm_phone = _normalize_phone_for_capi(phone)
    ph = _sha256(norm_phone)
    if ph:
        user_data["ph"] = [ph]
    fn = _sha256(first_name.split()[0] if first_name else None)
    if fn:
        user_data["fn"] = [fn]
    if client_ip:
        user_data["client_ip_address"] = client_ip
    if client_user_agent:
        user_data["client_user_agent"] = client_user_agent
    if fbc:
        user_data["fbc"] = fbc
    if fbp:
        user_data["fbp"] = fbp

    custom_data: dict[str, Any] = {}
    if value is not None:
        custom_data["value"] = float(value)
        custom_data["currency"] = currency
    if extra_custom_data:
        custom_data.update(extra_custom_data)

    event: dict[str, Any] = {
        "event_name":      event_name,
        "event_time":      int(time.time()),
        "event_id":        event_id,
        "action_source":   "website",
        "user_data":       user_data,
    }
    if event_source_url:
        event["event_source_url"] = event_source_url
    if custom_data:
        event["custom_data"] = custom_data

    payload = {"data": [event]}
    url = f"{_GRAPH}/{settings.meta_pixel_id}/events"
    params = {"access_token": settings.meta_capi_token}

    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.post(url, params=params, json=payload)
            if r.status_code in (200, 201):
                logger.info(
                    f"[Meta CAPI] {event_name} ok event_id={event_id[:8]}... "
                    f"(em={'y' if em else 'n'} ph={'y' if ph else 'n'} fbc={'y' if fbc else 'n'})"
                )
                return True
            logger.warning(f"[Meta CAPI] {event_name} retornou {r.status_code}: {r.text[:300]}")
    except Exception as e:
        logger.warning(f"[Meta CAPI] erro: {e}")
    return False
