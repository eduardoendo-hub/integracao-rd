"""
Cliente do RD Station Marketing — API de conversões com token público.

Para cada lead de uma campanha que tenha o bloco `rd_marketing` no registry,
registra uma **conversão** no RD Marketing. Um fluxo de automação do RD
Marketing com entrada "conversão `oferta-<oferta>`" manda o e-mail de
agradecimento e chama o webhook nativo do RD Conversas (template de WhatsApp
e fila de atendimento). Este serviço só registra a conversão; o conteúdo do
e-mail/WhatsApp fica no RD Marketing.

    POST https://api.rd.services/platform/conversions?api_key=<RDSM_API_KEY>
    {"event_type": "CONVERSION", "event_family": "CDP", "payload": {...}}

Regras:
  - `RDSM_API_KEY` vazio → no-op com log (deploy seguro antes do token existir).
  - Campanha sem bloco `rd_marketing` → não envia (LPs antigas não mudam).
  - A conversão exige e-mail; lead só com telefone → não envia (log).
  - Campos personalizados (`cf_*`) só saem se estiverem em `RDSM_CUSTOM_FIELDS`
    (lista CSV), porque campo inexistente no RD pode fazer a conversão ser recusada.
  - Logs nunca levam e-mail, telefone nem o token (a URL tem o api_key).
  - Nunca levanta exceção: roda em segundo plano depois da resposta ao navegador.
"""

import asyncio
import logging
import re
from typing import Any, Optional

import httpx

from app.core.config import settings
from app.models.lead import LeadIn

logger = logging.getLogger(__name__)

_URL = "https://api.rd.services/platform/conversions"
_TIMEOUT = httpx.Timeout(5.0, connect=3.0)
_RETRY_DELAY = 0.5

# Transporte HTTP opcional — os testes substituem por httpx.MockTransport.
_transport: Optional[httpx.AsyncBaseTransport] = None

# Campos personalizados que o serviço sabe preencher. Só são enviados os que
# estiverem listados em RDSM_CUSTOM_FIELDS (e que tenham valor).
KNOWN_CUSTOM_FIELDS = (
    "cf_oferta_curso",
    "cf_oferta_modalidade",
    "cf_oferta_turma",
    "cf_oferta_link",
)


def normalize_mobile_phone(raw: Optional[str]) -> Optional[str]:
    """Telefone no formato +55DDDNÚMERO. Retorna None se não der para normalizar."""
    digits = re.sub(r"\D", "", raw or "").lstrip("0")
    if len(digits) in (10, 11):            # DDD + número, sem DDI
        return "+55" + digits
    if len(digits) in (12, 13) and digits.startswith("55"):  # já com DDI 55
        return "+" + digits
    return None


def _first(*values: Any) -> Optional[str]:
    for v in values:
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _normalize_tag(tag: str) -> str:
    return re.sub(r"\s+", "-", tag.strip().lower())


def _custom_field_candidates(lead: LeadIn, cfg: dict) -> dict[str, Optional[str]]:
    extra = lead.extra or {}
    return {
        "cf_oferta_curso":      _first(extra.get("produto"), cfg.get("product_label")),
        "cf_oferta_modalidade": _first(extra.get("modalidade")),
        "cf_oferta_turma":      _first(extra.get("turma_descricao"), extra.get("turma")),
        "cf_oferta_link":       _first(extra.get("landing_page"), lead.source_page),
    }


def build_payload(lead: LeadIn, cfg: dict) -> Optional[dict]:
    """Monta o corpo da conversão. None se a campanha não usa RD Marketing ou falta e-mail."""
    block = cfg.get("rd_marketing")
    if not block or not block.get("conversion_identifier") or not lead.email:
        return None

    payload: dict[str, Any] = {
        "conversion_identifier": block["conversion_identifier"],
        "email": str(lead.email),
        "available_for_mailing": True,
        "legal_bases": [{
            "category": "communications",
            "type": settings.rdsm_legal_basis_type,
            "status": "granted",
        }],
    }
    if lead.name:
        payload["name"] = lead.name
    phone = normalize_mobile_phone(lead.phone)
    if phone:
        payload["mobile_phone"] = phone

    utm = lead.utm
    if utm:
        for key, value in (
            ("traffic_source", utm.source),
            ("traffic_medium", utm.medium),
            ("traffic_campaign", utm.campaign),
            ("traffic_value", utm.term),
        ):
            if value:
                payload[key] = value

    tags = [_normalize_tag(t) for t in (block.get("tags") or []) if isinstance(t, str) and t.strip()]
    if tags:
        payload["tags"] = list(dict.fromkeys(tags))

    allowed = set(settings.rdsm_custom_fields_list)
    for key, value in _custom_field_candidates(lead, cfg).items():
        if key in allowed and value:
            payload[key] = value

    return {"event_type": "CONVERSION", "event_family": "CDP", "payload": payload}


def _error_types(r: httpx.Response) -> str:
    """Só o tipo do erro do RD (a mensagem pode ecoar e-mail/telefone)."""
    try:
        data = r.json()
    except Exception:
        return "-"
    errors = data.get("errors") if isinstance(data, dict) else None
    if isinstance(errors, dict):
        errors = [errors]
    if isinstance(errors, list):
        types = [str(e.get("error_type")) for e in errors if isinstance(e, dict) and e.get("error_type")]
        if types:
            return ",".join(types)
    return "-"


async def send_conversion(lead: LeadIn, cfg: dict) -> bool:
    """Registra a conversão no RD Marketing. Retorna True se aceita. Nunca levanta."""
    slug = lead.campaign_slug
    try:
        if not cfg.get("rd_marketing"):
            return False
        if not settings.rdsm_api_key:
            logger.info(f"[RD Marketing] RDSM_API_KEY vazio — conversão ignorada campaign={slug}")
            return False
        body = build_payload(lead, cfg)
        if body is None:
            logger.warning(
                f"[RD Marketing] conversão não enviada campaign={slug} "
                f"(sem e-mail ou sem conversion_identifier)"
            )
            return False

        identifier = body["payload"]["conversion_identifier"]
        params = {"api_key": settings.rdsm_api_key}
        async with httpx.AsyncClient(timeout=_TIMEOUT, transport=_transport) as client:
            for attempt in (1, 2):
                try:
                    r = await client.post(_URL, params=params, json=body)
                except httpx.TransportError as e:  # timeout / conexão
                    logger.warning(
                        f"[RD Marketing] falha de rede campaign={slug} conversion={identifier} "
                        f"tentativa={attempt} erro={type(e).__name__}"
                    )
                    if attempt == 1:
                        await asyncio.sleep(_RETRY_DELAY)
                        continue
                    return False
                if r.status_code < 300:
                    logger.info(
                        f"[RD Marketing] conversão ok campaign={slug} conversion={identifier} "
                        f"status={r.status_code}"
                    )
                    return True
                if r.status_code >= 500 and attempt == 1:
                    logger.warning(
                        f"[RD Marketing] status={r.status_code} campaign={slug} — nova tentativa"
                    )
                    await asyncio.sleep(_RETRY_DELAY)
                    continue
                logger.warning(
                    f"[RD Marketing] conversão recusada campaign={slug} conversion={identifier} "
                    f"status={r.status_code} erro={_error_types(r)}"
                )
                return False
    except Exception as e:  # nunca derruba a task em segundo plano
        logger.error(f"[RD Marketing] erro inesperado campaign={slug} erro={type(e).__name__}")
    return False
