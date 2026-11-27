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

def _extract_contacts(data) -> list[dict]:
    contacts = data.get("contacts", data) if isinstance(data, dict) else data
    return [c for c in contacts if isinstance(c, dict)] if isinstance(contacts, list) else []


def _contact_emails(contact: dict) -> set[str]:
    out = set()
    for e in contact.get("emails") or []:
        val = (e.get("email") if isinstance(e, dict) else e) or ""
        if val.strip():
            out.add(val.strip().lower())
    return out


def _contact_phones(contact: dict) -> set[str]:
    """Telefones do contato normalizados (55 + DDD + número)."""
    out = set()
    for p in contact.get("phones") or []:
        val = (p.get("phone") if isinstance(p, dict) else p) or ""
        norm = _normalize_phone(val)
        if norm:
            out.add(norm)
    return out


def _pick_by_email(contacts: list[dict], email: str, phone: Optional[str]) -> Optional[dict]:
    """
    Só aceita contato que REALMENTE tem o e-mail pesquisado (a API v1 pode
    devolver resultados fora do filtro). Se houver vários, prefere o que também
    tem o telefone do lead.
    """
    target = email.strip().lower()
    matches = [c for c in contacts if target in _contact_emails(c)]
    if not matches:
        return None
    if phone:
        for c in matches:
            if phone in _contact_phones(c):
                return c
    return matches[0]


def _pick_by_phone(contacts: list[dict], phone: str, email: Optional[str]) -> Optional[dict]:
    """
    Só aceita contato que REALMENTE tem o telefone pesquisado. Se o lead trouxe
    e-mail, ignora contatos com OUTRO e-mail (telefone compartilhado = outra
    pessoa; não podemos pendurar o negócio nela). Prefere contato sem e-mail.
    """
    matches = [c for c in contacts if phone in _contact_phones(c)]
    if not email:
        return matches[0] if matches else None
    target = email.strip().lower()
    compatible = [c for c in matches if not _contact_emails(c) or target in _contact_emails(c)]
    return compatible[0] if compatible else None


async def find_contact_by_phone(
    client: httpx.AsyncClient, phone: str, email: Optional[str] = None
) -> Optional[dict]:
    if not phone:
        return None
    norm = _normalize_phone(phone)
    for variant in _phone_variants(norm):
        try:
            r = await client.get(f"{_BASE}/contacts", params=_params({"phone": variant}))
            if r.status_code != 200:
                continue
            found = _pick_by_phone(_extract_contacts(r.json()), norm, email)
            if found:
                return found
        except Exception as e:
            logger.warning(f"[RD CRM] find_contact_by_phone falhou variant={variant}: {e}")
    return None


async def find_contact_by_email(
    client: httpx.AsyncClient, email: str, phone: Optional[str] = None
) -> Optional[dict]:
    if not email:
        return None
    try:
        r = await client.get(f"{_BASE}/contacts", params=_params({"email": email.strip()}))
        if r.status_code != 200:
            return None
        return _pick_by_email(_extract_contacts(r.json()), email, _normalize_phone(phone) if phone else None)
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


def _source_campaign_payload(deal_source_id: Optional[str], campaign_id: Optional[str]) -> dict:
    out: dict = {}
    if deal_source_id:
        out["deal_source"] = {"_id": deal_source_id}
    if campaign_id:
        out["campaign"] = {"_id": campaign_id}
    return out


def _ref_id(obj) -> Optional[str]:
    if isinstance(obj, dict):
        return obj.get("_id") or obj.get("id")
    return obj if isinstance(obj, str) else None


async def set_deal_source_and_campaign(
    client: httpx.AsyncClient,
    *,
    deal_id: str,
    deal_envelope: Optional[dict],
    deal_source_id: Optional[str],
    campaign_id: Optional[str],
) -> None:
    """Garante Fonte/Campanha no negócio. Se o POST /deals já gravou, não faz nada;
    senão faz PUT /deals/{id}. Falha vira só log (o lead já foi criado)."""
    if not (deal_source_id or campaign_id):
        return
    env = deal_envelope if isinstance(deal_envelope, dict) else {}
    ok_source = not deal_source_id or _ref_id(env.get("deal_source")) == deal_source_id
    ok_campaign = not campaign_id or _ref_id(env.get("campaign")) == campaign_id
    if ok_source and ok_campaign:
        return
    payload = {"deal": {}}
    payload.update(_source_campaign_payload(deal_source_id, campaign_id))
    try:
        r = await client.put(f"{_BASE}/deals/{deal_id}", params=_params(), json=payload)
        if r.status_code in (200, 201, 204):
            logger.info(f"[RD CRM] Deal {deal_id}: fonte/campanha gravadas via PUT")
        else:
            logger.warning(f"[RD CRM] PUT /deals/{deal_id} (fonte/campanha) retornou {r.status_code}: {r.text[:200]}")
    except Exception as e:
        logger.warning(f"[RD CRM] Falha ao gravar fonte/campanha no deal {deal_id}: {e}")


async def create_deal(
    client: httpx.AsyncClient,
    *,
    deal_name: str,
    contact_id: str,
    deal_stage_id: str,
    custom_fields: Optional[dict] = None,
    tags: Optional[list[str]] = None,
    description: Optional[str] = None,
    deal_source_id: Optional[str] = None,
    campaign_id: Optional[str] = None,
) -> Optional[dict]:
    """
    Cria deal no funil/etapa configurados.

    `deal_source_id` / `campaign_id` (opcionais) marcam a Fonte e a Campanha do
    negócio no RD CRM. As páginas de oferta usam isso para o marketing achar os
    negócios mesmo depois de o vendedor renomear (o nome muda; fonte e campanha não).

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
        # 'note' (singular) é o campo que aparece como "Anotações" no Deal do RD CRM v1.
        # 'description' não aparecia em testes anteriores.
        deal_obj["note"] = description
    if custom_fields:
        deal_obj["deal_custom_fields"] = [
            {"custom_field_id": k, "value": v} for k, v in custom_fields.items() if v
        ]
    if tags:
        # tags em CRM v1 normalmente vão em campain/contact, mas tentamos no deal também
        deal_obj["tags"] = tags

    # RD CRM v1: contacts vai TOP-LEVEL do payload (irmão de deal), não dentro
    # do deal. Formato esperado: [{"_id": "<id>"}] (com underscore).
    payload = {
        "deal":     deal_obj,
        "contacts": [{"_id": contact_id}],
    }
    # RD CRM v1: campaign e deal_source também vão TOP-LEVEL ({"_id": ...}).
    payload.update(_source_campaign_payload(deal_source_id, campaign_id))

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
    Vincula contato ao deal. RD CRM v1 nao expoe um campo de contacts
    confiavel no POST /deals — a vinculacao mais robusta e' via PUT no
    contato, adicionando o deal_id na lista deal_ids do contato.
    """
    # 1. Buscar contato pra ler deal_ids existentes
    try:
        r = await client.get(f"{_BASE}/contacts/{contact_id}", params=_params())
        if r.status_code != 200:
            logger.warning(f"[RD CRM] GET /contacts/{contact_id} retornou {r.status_code}")
            return False
        contact = r.json()
    except Exception as e:
        logger.warning(f"[RD CRM] Falha ao GET contato {contact_id}: {e}")
        return False

    deal_ids = list(contact.get("deal_ids") or [])
    if deal_id in deal_ids:
        return True  # ja vinculado

    deal_ids.append(deal_id)
    payload = {"deal_ids": deal_ids}
    try:
        r = await client.put(f"{_BASE}/contacts/{contact_id}", params=_params(), json=payload)
        if r.status_code in (200, 201, 204):
            logger.info(f"[RD CRM] Contato {contact_id} agora linka {len(deal_ids)} deal(s) (incluindo {deal_id})")
            return True
        logger.warning(
            f"[RD CRM] PUT /contacts/{contact_id} (deal_ids) retornou {r.status_code}: {r.text[:300]}"
        )
    except Exception as e:
        logger.warning(f"[RD CRM] Falha ao vincular contato ao deal {deal_id}: {e}")
    return False


async def delete_deal(deal_id: str) -> bool:
    """
    Remove uma oportunidade (deal) do RD CRM: DELETE /deals/{id}.

    Usado quando um lead que se cadastrou no Engaged (e ganhou um deal) depois
    COMPRA — o comprador nao deve ficar com oportunidade aberta no funil de
    vendas. Retorna True se removeu (ou se ja nao existia / 404).
    """
    if not settings.rd_crm_token:
        logger.error("[RD CRM] RD_CRM_TOKEN ausente — delete_deal ignorado")
        return False
    if not deal_id:
        return False
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        try:
            r = await client.delete(f"{_BASE}/deals/{deal_id}", params=_params())
            if r.status_code in (200, 204):
                logger.info(f"[RD CRM] Deal {deal_id} removido")
                return True
            if r.status_code == 404:
                logger.info(f"[RD CRM] Deal {deal_id} ja nao existe (404) — ok")
                return True
            logger.warning(f"[RD CRM] DELETE /deals/{deal_id} retornou {r.status_code}: {r.text[:200]}")
        except Exception as e:
            logger.error(f"[RD CRM] Erro ao remover deal {deal_id}: {e}")
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
    Anexa uma nota/atividade ao deal. RD CRM v1 usa /activities como
    endpoint canonico para notas (BOT-SDR-PJ confirmado). Tenta varios
    formatos pq a doc do RD CRM v1 e' inconsistente:

      1) POST /activities  com {activity: {deal_id, text, type:"note"}}
      2) POST /deal_notes  com {deal_note: {deal_id, content}}
      3) POST /deal_notes  com {deal_id, content}   (sem envelope)

    Retorna True na primeira que responder 200/201.
    """
    attempts = [
        (f"{_BASE}/activities", {"activity": {"deal_id": deal_id, "text": content, "type": "note"}}),
        (f"{_BASE}/activities", {"deal_id": deal_id, "text": content, "type": "note"}),
        (f"{_BASE}/deal_notes", {"deal_note": {"deal_id": deal_id, "content": content}}),
        (f"{_BASE}/deal_notes", {"deal_id": deal_id, "content": content}),
    ]
    for url, payload in attempts:
        try:
            r = await client.post(url, params=_params(), json=payload)
            if r.status_code in (200, 201):
                logger.info(f"[RD CRM] Nota criada via {url} payload_keys={list(payload.keys())}")
                return True
            logger.warning(
                f"[RD CRM] {url} retornou {r.status_code}: {r.text[:200]}"
            )
        except Exception as e:
            logger.warning(f"[RD CRM] Falha em {url}: {e}")
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
    deal_source_id: Optional[str] = None,
    campaign_id: Optional[str] = None,
) -> dict:
    """
    Garante contato (busca por e-mail, depois telefone compatível; cria se necessário) e cria deal.
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
        # E-mail primeiro (identifica a pessoa); telefone só como fallback e
        # nunca casando com contato que tenha outro e-mail.
        contact = None
        if email:
            contact = await find_contact_by_email(client, email, norm_phone)
        if not contact and norm_phone:
            contact = await find_contact_by_phone(client, norm_phone, email)

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
            deal_source_id=deal_source_id,
            campaign_id=campaign_id,
        )
        # O RD CRM v1 retorna o deal com diferentes formatos de envelope.
        # Buscamos tanto top-level quanto em data["deal"].
        if isinstance(deal, dict):
            deal_envelope = deal.get("deal") if isinstance(deal.get("deal"), dict) else deal
        else:
            deal_envelope = {}
        deal_id = (deal_envelope.get("_id") or deal_envelope.get("id")) if isinstance(deal_envelope, dict) else None

        # SEMPRE vincular contato ao deal via PUT no contato — POST /deals
        # ignora 'contacts' no payload no RD CRM v1 (testado: nunca cria vinculo).
        if deal_id and contact_id:
            await link_contact_to_deal(client, deal_id=deal_id, contact_id=contact_id)

        if deal_id:
            await set_deal_source_and_campaign(
                client,
                deal_id=deal_id,
                deal_envelope=deal_envelope,
                deal_source_id=deal_source_id,
                campaign_id=campaign_id,
            )

        # SEMPRE criar deal_note com a description — o campo 'note' no payload
        # do POST /deals tambem e' ignorado. /deal_notes e' o endpoint dedicado.
        if deal_id and description:
            await create_deal_note(client, deal_id=deal_id, content=description)

        return {
            "contact_id": contact_id,
            "deal_id":    deal_id,
            "status":     "created" if deal_id else "skipped",
        }
