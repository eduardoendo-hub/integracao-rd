import logging

from fastapi import APIRouter, HTTPException

from app.campaigns.registry import get_campaign
from app.models.lead import LeadIn, LeadOut, WhatsAppClickIn
from app.services import iris_webhook, rd_crm

logger = logging.getLogger(__name__)
router = APIRouter()


_CHANNEL_LABELS = {
    "form":     "Formulário",
    "whatsapp": "WhatsApp",
    "email":    "E-mail",
    "phone":    "Telefone",
}


def _interpolate(template: str, lead: LeadIn) -> str:
    """Resolve placeholders {name}, {perfil}, {channel}, {utm.source}, etc."""
    if not isinstance(template, str) or "{" not in template:
        return template
    out = template
    out = out.replace("{name}", lead.name or "")
    out = out.replace("{perfil}", lead.perfil or "")
    out = out.replace("{source_page}", lead.source_page or "")
    out = out.replace("{channel}", lead.channel or "form")
    out = out.replace("{channel_label}", _CHANNEL_LABELS.get(lead.channel or "form", lead.channel or ""))
    if lead.utm:
        out = out.replace("{utm.source}",   lead.utm.source or "")
        out = out.replace("{utm.medium}",   lead.utm.medium or "")
        out = out.replace("{utm.campaign}", lead.utm.campaign or "")
        out = out.replace("{utm.content}",  lead.utm.content or "")
        out = out.replace("{utm.term}",     lead.utm.term or "")
    else:
        for key in ("source", "medium", "campaign", "content", "term"):
            out = out.replace("{utm." + key + "}", "")
    return out


def _resolve_custom_fields(template: dict, lead: LeadIn) -> dict:
    return {k: _interpolate(v, lead) for k, v in (template or {}).items()}


@router.post("/leads", response_model=LeadOut)
async def create_lead(lead: LeadIn) -> LeadOut:
    """Recebe um Lead de qualquer LP, cria Contact+Deal no RD CRM e notifica o IRIS."""
    cfg = get_campaign(lead.campaign_slug)
    if not cfg:
        raise HTTPException(status_code=404, detail=f"Campanha desconhecida: {lead.campaign_slug}")

    deal_name = _interpolate(cfg.get("deal_name_tpl", "Lead — {name}"), lead)
    custom_fields = _resolve_custom_fields(cfg.get("custom_fields", {}), lead)
    # Tags do registry sao interpoladas (suportam {channel}). Adiciona tag de
    # canal automatica para qualquer canal nao explicitado no registry.
    tags = [_interpolate(t, lead) for t in (cfg.get("tags") or [])]
    canal_tag = "canal:" + (lead.channel or "form")
    if canal_tag not in tags:
        tags.append(canal_tag)

    result = await rd_crm.upsert_contact_and_create_deal(
        name=lead.name,
        email=lead.email,
        phone=lead.phone,
        deal_name=deal_name,
        deal_stage_id=cfg["deal_stage_id"],
        custom_fields=custom_fields,
        tags=tags,
    )

    iris_webhook.emit("lead.created", {
        "campaign_slug": lead.campaign_slug,
        "name":    lead.name,
        "email":   lead.email,
        "phone":   lead.phone,
        "perfil":  lead.perfil,
        "channel": lead.channel,
        "utm":     lead.utm.model_dump() if lead.utm else None,
        "source_page": lead.source_page,
        "rd_crm":  result,
    })

    logger.info(
        f"[lead] campaign={lead.campaign_slug} status={result['status']} "
        f"contact_id={result['contact_id']} deal_id={result['deal_id']}"
    )

    return LeadOut(**result)


@router.post("/leads/whatsapp-click")
async def whatsapp_click(payload: WhatsAppClickIn) -> dict:
    """Apenas registra o clique no WhatsApp e notifica o IRIS — não cria deal."""
    iris_webhook.emit("whatsapp.click", {
        "campaign_slug": payload.campaign_slug,
        "phone": payload.phone,
        "source_page": payload.source_page,
        "utm": payload.utm.model_dump() if payload.utm else None,
    })
    return {"status": "ok"}


@router.get("/campaigns/{slug}")
async def get_campaign_config(slug: str) -> dict:
    cfg = get_campaign(slug)
    if not cfg:
        raise HTTPException(status_code=404, detail="Campanha desconhecida")
    return cfg
