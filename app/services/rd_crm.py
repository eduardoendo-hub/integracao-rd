"""
Cliente do RD Station CRM (API v1).

Autenticação simples via token de API (sem OAuth2).
Token em: CRM → avatar → Integrações → Token API.

Endpoints centrais usados aqui:
  GET  /contacts?phone={phone}&token=...   — busca contato pelo telefone
  GET  /contacts?email={email}&token=...   — busca contato pelo email
  POST /contacts?token=...                 — cria contato
  POST /deals?token=...                    — cria deal (negociação) num funil/etapa

Padrão portado do BOT-SDR-PJ (~/Documents/Claude/Projects/BOT-SDR-PJ/app/services/rd_crm.py),
com adição das funções de **escrita** (create_contact, create_deal).
"""

import logging
import re
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_BASE = "https://crm.rdstation.com/api/v1"
_TIMEOUT = 10


def _params(extra: Optional[dict] = None) -> dict:
    """Retorna dict de query params já com token."""
    p = {"token": settings.rd_crm_token}
    if extra:
        p.update({k: v for k, v in extra.items() if v is not None})
    return p


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de telefone
# ─────────────────────────────────────────────────────────────────────────────

def _clean_phone(raw: str) -> str:
    """Remove tudo que não é dígito."""
    return re.sub(r"\D", "", raw or "")


def _normalize_phone(raw: str) -> str:
    """Normaliza para formato 55XXXXXXXXXXX (DDI Brasil)."""
    digits = _clean_phone(raw)
    if not digits:
        return ""
    if len(digits) in (10, 11) and not digits.startswith("55"):
        return "55" + digits
    return digits


def _phone_variants(phone: str) -> list[str]:
    """Variantes para tentar busca: com e sem DDI."""
    variants = [phone]
    if phone.startswith("55") and len(phone) >= 12:
        variants.append(phone[2:])
    elif len(phone) <= 11:
        variants.append("55" + phone)
    return variants


# ─────────────────────────────────────────────────────────────────────────────
# Read: find contact
# ─────────────────────────────────────────────────────────────────────────────

async def find_contact_by_phone(client: httpx.AsyncClient, phone: str) -> Optional[dict]:
    if not phone:
        return None
    for variant in _phone_variants(phone):
        try:
            r = await client.get(f"{_BASE}/contacts", params=_params({"phone": variant}))
            if r.status_code != 200:
                continue
            data = r.json()
            contacts = data.get("contacts", data) if isinstance(data, dict) else data
            if contacts and isinstance(contacts, list) and contacts:
                return contacts[0]
        except Exception as e:
            logger.warning(f"[RD CRM] find_contact_by_phone falhou variant={variant}: {e}")
    return None


async def find_contact_by_email(client: httpx.AsyncClient, email: str) -> Optional[dict]:
    if not email:
        return None
    try:
        r = await client.get(f"{_BASE}/contacts", params=_params({"email": email}))
        if r.status_code != 200:
            return None
        data = r.json()
        contacts = data.get("contacts", data) if isinstance(data, dict) else data
        if contacts and isinstance(contacts, list) and contacts:
            return contacts[0]
    except Exception as e:
        logger.warning(f"[RD CRM] find_contact_by_email falhou email={email}: {e}")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Write: create contact / create deal
# ─────────────────────────────────────────────────────────────────────────────

async def create_contact(
    client: httpx.AsyncClient,
    *,
    name: Optional[str],
    email: Optional[str],
    phone: Optional[str],
) -> Optional[dict]:
    """Cria contato no RD CRM. Retorna o objeto criado ou None em falha."""
    safe_name = name or (email.split("@")[0] if email else "Lead sem nome")
    payload: dict = {"name": safe_name}
    if email:
        payload["emails"] = [{"email": email}]
    if phone:
        payload["phones"] = [{"phone": phone, "type": "cellphone"}]

    try:
        r = await client.post(f"{_BASE}/contacts", params=_params(), json=payload)
        if r.status_code in (200, 201):
            logger.info(f"[RD CRM] Contato criado: name='{safe_name}' email='{email}' phone='{phone}'")
            return r.json()
        logger.warning(f"[RD CRM] POST /contacts retornou {r.status_code}: {r.text[:300]}")
        return None
    except Exception as e:
        logger.error(f"[RD CRM] Erro ao criar contato: {e}")
        return None


async def update_contact_if_missing(
    client: httpx.AsyncClient,
    *,
    contact_id: str,
    contact_obj: dict,
    name: Optional[str],
    email: Optional[str],
    phone: Optional[str],
) -> None:
    """
    Se o contato existente está sem nome/email/phone que recebemos do form,
    faz PATCH para incrementar (NUNCA sobrescreve dados existentes).
    Útil quando achamos um contato antigo com phone e o form trouxe email novo
    (ou vice-versa).
    """
    patch: dict = {}

    existing_emails = contact_obj.get("emails") or []
    has_email = any((e.get("email") or "").strip() for e in existing_emails) if isinstance(existing_emails, list) else False
    if email and not has_email:
        patch["emails"] = [{"email": email}]

    existing_phones = contact_obj.get("phones") or []
    has_phone = any((p.get("phone") or "").strip() for p in existing_phones) if isinstance(existing_phones, list) else False
    if phone and not has_phone:
        patch["phones"] = [{"phone": phone, "type": "cellphone"}]

    existing_name = (contact_obj.get("name") or "").strip()
    is_placeholder = (not existing_name) or existing_name.lower() in ("lead sem nome", "lead", "?")
    if name and is_placeholder:
        patch["name"] = name

    if not patch:
        return  # nada a atualizar

    try:
        r = await client.put(f"{_BASE}/contacts/{contact_id}", params=_params(), json=patch)
        if r.status_code in (200, 201, 204):
            logger.info(f"[RD CRM] Contato {contact_id} incrementado com {list(patch.keys())}")
        else:
            logger.warning(f"[RD CRM] PUT /contacts/{contact_id} retornou {r.status_code}: {r.text[:200]}")
    except Exception as e:
        logger.warning(f"[RD CRM] Falha ao atualizar contato {contact_id}: {e}")


async def create_deal(
    client: httpx.AsyncClient,
    *,
    deal_name: str,
    contact_id: str,
    deal_stage_id: str,
    custom_fields: Optional[dict] = None,
    tags: Optional[list[str]] = None,
    description: Optional[str] = None,
) -> Optional[dict]:
    """
    Cria deal no funil/etapa configurados.

    O endpoint `POST /deals` exige um payload aninhado:
      {
        "deal":     { "deal_stage_id": "...", "name": "...", "description": "..." },
        "contacts": [ { "id": "<contact_id>" } ]
      }

    `description` aparece como texto principal/anotações no Deal — onde o
    vendedor lê os dados detalhados do lead (nome, email, phone, UTM).
    """
    deal_obj: dict = {
        "deal_stage_id": deal_stage_id,
        "name": deal_name,
    }
    if description:
        deal_obj["description"] = description
    if custom_fields:
        deal_obj["deal_custom_fields"] = [
            {"custom_field_id": k, "value": v} for k, v in custom_fields.items() if v
        ]

    # RD CRM v1 aceita contacts como [{"_id": "<id>"}] (campo com underscore).
    # Tentando "id" sem underscore o vinculo nao e' criado mesmo respondendo 201.
    payload = {
        "deal":     deal_obj,
        "contacts": [{"_id": contact_id}],
    }
    if tags:
        payload["tags"] = tags

    try:
        r = await client.post(f"{_BASE}/deals", params=_params(), json=payload)
        if r.status_code in (200, 201):
            data = r.json()
            # Loga o que o RD CRM retornou pra diagnosticar vinculacao
            deal_obj_resp = data.get("deal") if isinstance(data.get("deal"), dict) else data
            contacts_resp = data.get("contacts") or (deal_obj_resp.get("contacts") if isinstance(deal_obj_resp, dict) else None) or []
            logger.info(
                f"[RD CRM] Deal criado: id={(deal_obj_resp or {}).get('_id') or (deal_obj_resp or {}).get('id')} "
                f"contacts_no_response={len(contacts_resp) if isinstance(contacts_resp, list) else '?'}"
            )
            return data
        logger.warning(f"[RD CRM] POST /deals retornou {r.status_code}: {r.text[:300]}")
        return None
    except Exception as e:
        logger.error(f"[RD CRM] Erro ao criar deal: {e}")
        return None


async def link_contact_to_deal(
    client: httpx.AsyncClient,
    *,
    deal_id: str,
    contact_id: str,
) -> bool:
    """
    Fallback: vincula contato ao deal via PUT /deals/{id}.
    Usado caso a vinculacao via POST /deals nao tenha pegado.
    """
    payload = {"deal": {"contacts": [{"_id": contact_id}]}}
    try:
        r = await client.put(f"{_BASE}/deals/{deal_id}", params=_params(), json=payload)
        if r.status_code in (200, 201, 204):
            logger.info(f"[RD CRM] Contato {contact_id} vinculado ao deal {deal_id} via PUT")
            return True
        logger.warning(f"[RD CRM] PUT /deals/{deal_id} (link contact) retornou {r.status_code}: {r.text[:200]}")
    except Exception as e:
        logger.warning(f"[RD CRM] Falha ao vincular contato ao deal {deal_id}: {e}")
    return False


async def get_deal(client: httpx.AsyncClient, deal_id: str) -> Optional[dict]:
    """GET /deals/{id} — usado por rota de debug."""
    try:
        r = await client.get(f"{_BASE}/deals/{deal_id}", params=_params())
        if r.status_code == 200:
            return r.json()
        logger.warning(f"[RD CRM] GET /deals/{deal_id} retornou {r.status_code}")
    except Exception as e:
        logger.warning(f"[RD CRM] Erro ao buscar deal {deal_id}: {e}")
    return None


async def create_deal_note(
    client: httpx.AsyncClient,
    *,
    deal_id: str,
    content: str,
) -> bool:
    """
    Anexa uma nota ao deal via /deal_notes. Usado como fallback caso
    description não apareça no UI do RD CRM (depende da configuração).
    """
    payload = {"deal_note": {"deal_id": deal_id, "content": content}}
    try:
        r = await client.post(f"{_BASE}/deal_notes", params=_params(), json=payload)
        if r.status_code in (200, 201):
            return True
        logger.warning(f"[RD CRM] POST /deal_notes retornou {r.status_code}: {r.text[:200]}")
    except Exception as e:
        logger.warning(f"[RD CRM] Falha ao criar deal_note: {e}")
    return False


# ─────────────────────────────────────────────────────────────────────────────
# High-level: upsert contact + create deal
# ─────────────────────────────────────────────────────────────────────────────

async def upsert_contact_and_create_deal(
    *,
    name: Optional[str],
    email: Optional[str],
    phone: Optional[str],
    deal_name: str,
    deal_stage_id: str,
    custom_fields: Optional[dict] = None,
    tags: Optional[list[str]] = None,
    description: Optional[str] = None,
) -> dict:
    """
    Garante contato (busca por phone, depois email; cria se necessário) e cria deal.
    Se o contato já existir mas estiver sem name/email/phone, faz PATCH para
    incrementar com os dados que vieram do form (sem sobrescrever existentes).

    Retorna {contact_id, deal_id, status}, onde status é "created" (deal criado) ou
    "skipped" (sem token / falha).
    """
    if not settings.rd_crm_token:
        logger.error("[RD CRM] RD_CRM_TOKEN ausente — operação ignorada")
        return {"contact_id": None, "deal_id": None, "status": "skipped"}

    norm_phone = _normalize_phone(phone) if phone else None

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        contact = None
        if norm_phone:
            contact = await find_contact_by_phone(client, norm_phone)
        if not contact and email:
            contact = await find_contact_by_email(client, email)

        if not contact:
            contact = await create_contact(client, name=name, email=email, phone=norm_phone)
            if not contact:
                return {"contact_id": None, "deal_id": None, "status": "skipped"}

        contact_id = contact.get("_id") or contact.get("id")
        if not contact_id:
            return {"contact_id": None, "deal_id": None, "status": "skipped"}

        # Se o contato existia mas estava sem dados, incrementa
        await update_contact_if_missing(
            client,
            contact_id=contact_id,
            contact_obj=contact,
            name=name,
            email=email,
            phone=norm_phone,
        )

        deal = await create_deal(
            client,
            deal_name=deal_name,
            contact_id=contact_id,
            deal_stage_id=deal_stage_id,
            custom_fields=custom_fields,
            tags=tags,
            description=description,
        )
        # O RD CRM v1 retorna o deal com diferentes formatos de envelope.
        # Buscamos tanto top-level quanto em data["deal"].
        if isinstance(deal, dict):
            deal_envelope = deal.get("deal") if isinstance(deal.get("deal"), dict) else deal
        else:
            deal_envelope = {}
        deal_id = (deal_envelope.get("_id") or deal_envelope.get("id")) if isinstance(deal_envelope, dict) else None

        # Fallback 1: vincular contato ao deal via PUT, caso o POST nao tenha
        # vinculado automaticamente (alguns tenants do RD CRM exigem)
        if deal_id and contact_id:
            contacts_in_deal = deal_envelope.get("contacts") if isinstance(deal_envelope, dict) else None
            has_link = bool(contacts_in_deal) if isinstance(contacts_in_deal, list) else False
            if not has_link:
                await link_contact_to_deal(client, deal_id=deal_id, contact_id=contact_id)

        # Fallback 2: se description nao foi aceita pela API mas conseguimos
        # criar o deal, anexa como deal_note separado.
        if deal_id and description:
            desc_in_deal = (deal_envelope.get("description") or "").strip() if isinstance(deal_envelope, dict) else ""
            if not desc_in_deal:
                await create_deal_note(client, deal_id=deal_id, content=description)

        return {
            "contact_id": contact_id,
            "deal_id":    deal_id,
            "status":     "created" if deal_id else "skipped",
        }
