"""
Endpoint que recebe eventos do client-side e dispara via Meta CAPI server-side.

Fluxo:
  1. Browser carrega o Pixel client (fbevents.js) e dispara evento (PageView, Lead, etc.).
  2. Browser envia POST aqui com {event_name, event_id (UUID), email, phone, fbc, fbp, ...}.
  3. Servidor faz hash dos PII e chama Meta Graph /events.
  4. Meta deduplica entre browser+servidor pelo mesmo event_id.

Sem CAPI, iOS 14+ e Brave/Firefox cortam 30-50% das conversões.
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel

from app.services import meta_capi

logger = logging.getLogger(__name__)
router = APIRouter()


class PixelEventIn(BaseModel):
    event_name: str
    event_id: str
    email: Optional[str] = None
    phone: Optional[str] = None
    first_name: Optional[str] = None
    event_source_url: Optional[str] = None
    fbc: Optional[str] = None
    fbp: Optional[str] = None
    value: Optional[float] = None
    currency: str = "BRL"
    extra: Optional[dict[str, Any]] = None


@router.post("/pixel/event")
async def pixel_event(
    payload: PixelEventIn,
    request: Request,
    user_agent: Optional[str] = Header(default=None, alias="User-Agent"),
) -> dict:
    """Recebe evento do client e dispara CAPI server-side."""
    client_ip = request.client.host if request.client else None
    # Se atrás de proxy (Coolify/Traefik), pega o IP real
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()

    sent = await meta_capi.send_event(
        event_name=payload.event_name,
        event_id=payload.event_id,
        email=payload.email,
        phone=payload.phone,
        first_name=payload.first_name,
        event_source_url=payload.event_source_url,
        client_ip=client_ip,
        client_user_agent=user_agent,
        fbc=payload.fbc,
        fbp=payload.fbp,
        value=payload.value,
        currency=payload.currency,
        extra_custom_data=payload.extra,
    )
    return {"sent": sent}
