import logging

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException

from app.campaigns.registry import get_campaign
from app.core.config import settings
from app.models.lead import LeadIn, LeadOut, WhatsAppClickIn
from app.services import iris_webhook, rd_crm, rd_marketing

logger = logging.getLogger(__name__)
router = APIRouter()


_CHANNEL_LABELS = {
    "form":     "Formulário",
    "whatsapp": "WhatsApp",
    "email":    "E-mail",
    "phone":    "Telefone",
    "engaged":  "Cadastro Engaged",
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


# Campos conhecidos de `extra`, com o rótulo que o vendedor vê no negócio.
# Campos fora destas listas continuam aparecendo em "OUTROS DADOS".
_EXTRA_INTERESSE = (
    ("produto", "Curso"),
    ("para", "É para"),
    ("empresa", "Empresa"),
    ("cargo", "Cargo"),
    ("modalidade", "Modalidade"),
    ("turma_descricao", "Turma escolhida"),
    ("turma", "Código da turma"),
    ("turno", "Turno"),
    ("mensagem", "Mensagem"),
)
_EXTRA_RASTREIO = (
    ("landing_page", "Página"),
    ("referrer", "Veio de"),
    ("primeiro_toque", "Primeiro contato (UTM)"),
    ("gclid", "gclid (Google Ads)"),
    ("gbraid", "gbraid (Google Ads)"),
    ("wbraid", "wbraid (Google Ads)"),
    ("fbclid", "fbclid (Meta)"),
    ("fbc", "_fbc (Meta)"),
    ("fbp", "_fbp (Meta)"),
    ("utm_id", "utm_id"),
    ("event_id", "ID do evento"),
)


def _build_lead_description(lead: LeadIn, cfg: dict | None = None) -> str:
    """
    Texto que vai como `description` do Deal no RD CRM. Vendedor abre o Deal
    e ja ve TODOS os dados que o lead deixou no formulario, sem precisar
    abrir o contato vinculado.
    """
    chan = _CHANNEL_LABELS.get(lead.channel or "form", lead.channel or "Formulário")
    product_label = (cfg.get("product_label") if cfg else None) or "Lead"
    lines = [
        f"📥 Lead capturado via LP - {product_label} [{chan}]",
        "",
        "DADOS DO LEAD",
        f"  Nome:     {lead.name or '(não informado)'}",
        f"  E-mail:   {lead.email or '(não informado)'}",
        f"  WhatsApp: {lead.phone or '(não informado)'}",
    ]
    if lead.perfil:
        lines.append(f"  Perfil:   {lead.perfil}")
    if lead.source_page:
        lines.append("")
        lines.append(f"PÁGINA DE ORIGEM")
        lines.append(f"  {lead.source_page}")
    if lead.utm and any([lead.utm.source, lead.utm.medium, lead.utm.campaign,
                         lead.utm.content, lead.utm.term]):
        lines.append("")
        lines.append("UTM (campanha de mídia)")
        if lead.utm.source:   lines.append(f"  source:   {lead.utm.source}")
        if lead.utm.medium:   lines.append(f"  medium:   {lead.utm.medium}")
        if lead.utm.campaign: lines.append(f"  campaign: {lead.utm.campaign}")
        if lead.utm.content:  lines.append(f"  content:  {lead.utm.content}")
        if lead.utm.term:     lines.append(f"  term:     {lead.utm.term}")
    if lead.extra:
        clean = {k: v for k, v in lead.extra.items() if v not in (None, "", [], {})}
        # Interesse primeiro (o que o vendedor usa no contato), depois o
        # rastreamento (para atribuição), e qualquer outro campo por último.
        for titulo, campos in (("INTERESSE", _EXTRA_INTERESSE), ("RASTREAMENTO", _EXTRA_RASTREIO)):
            linhas = [f"  {rotulo}: {clean.pop(chave)}" for chave, rotulo in campos if chave in clean]
            if linhas:
                lines.append("")
                lines.append(titulo)
                lines.extend(linhas)
        if clean:
            lines.append("")
            lines.append("OUTROS DADOS")
            for k, v in clean.items():
                lines.append(f"  {k}: {v}")
    return "\n".join(lines)


@router.post("/leads", response_model=LeadOut)
async def create_lead(lead: LeadIn, background_tasks: BackgroundTasks) -> LeadOut:
    """
    Recebe um Lead de qualquer LP, cria Contact+Deal no RD CRM e notifica o IRIS.
    Se a campanha tiver o bloco `rd_marketing` no registry, registra também uma
    conversão no RD Station Marketing (em segundo plano, depois da resposta).
    """
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

    description = _build_lead_description(lead, cfg)

    result = await rd_crm.upsert_contact_and_create_deal(
        name=lead.name,
        email=lead.email,
        phone=lead.phone,
        deal_name=deal_name,
        deal_stage_id=cfg["deal_stage_id"],
        custom_fields=custom_fields,
        tags=tags,
        description=description,
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

    # Conversão no RD Marketing (e-mail de agradecimento + WhatsApp via fluxo de
    # automação). Roda depois da resposta; falhas viram só log, sem dados pessoais.
    if cfg.get("rd_marketing"):
        background_tasks.add_task(rd_marketing.send_conversion, lead, cfg)

    return LeadOut(**result)


# Campos de atribuição do clique que seguem para o IRIS (o resto do `extra` fica de fora).
_ATRIBUICAO_WHATS = (
    "canal", "canal_primeiro", "primeiro_toque", "ultimo_toque", "utm_id", "adgroup", "utm_placement",
    "matchtype", "network", "gclid", "gbraid", "wbraid", "fbclid", "msclkid", "clique_tipo", "landing_page",
)


@router.post("/leads/whatsapp-click")
async def whatsapp_click(payload: WhatsAppClickIn) -> dict:
    """Apenas registra o clique no WhatsApp e notifica o IRIS — não cria deal.

    O IRIS guarda o pacote inteiro (Lead.rawJson). O wa_ref liga a conversa do WhatsApp ao clique;
    do `extra` vão só os campos de atribuição (sem fbc/fbp/ga_client_id).
    """
    atribuicao = {k: payload.extra.get(k) for k in _ATRIBUICAO_WHATS if payload.extra.get(k) not in (None, "")}
    iris_webhook.emit("whatsapp.click", {
        "campaign_slug": payload.campaign_slug,
        "phone": payload.phone,
        "source_page": payload.source_page,
        "utm": payload.utm.model_dump() if payload.utm else None,
        "wa_ref": payload.wa_ref,
        "placement": payload.placement,
        "oferta": payload.oferta,
        "atribuicao": atribuicao,
    })
    return {"status": "ok"}


@router.delete("/deals/{deal_id}")
async def delete_deal_endpoint(
    deal_id: str,
    x_iris_secret: str | None = Header(default=None),
) -> dict:
    """
    Remove uma oportunidade do RD CRM. Chamado server-to-server pelo IRIS
    quando um lead Engaged (que ganhou um deal ao se cadastrar) depois compra.

    Auth: header X-Iris-Secret == settings.iris_webhook_secret (mesmo segredo
    compartilhado usado nos webhooks IRIS↔integracao-rd). Endpoint destrutivo,
    entao exige o segredo configurado — sem ele, 401.
    """
    if not settings.iris_webhook_secret or x_iris_secret != settings.iris_webhook_secret:
        raise HTTPException(status_code=401, detail="unauthorized")
    ok = await rd_crm.delete_deal(deal_id)
    return {"status": "deleted" if ok else "failed", "deal_id": deal_id}


@router.get("/campaigns/{slug}")
async def get_campaign_config(slug: str) -> dict:
    cfg = get_campaign(slug)
    if not cfg:
        raise HTTPException(status_code=404, detail="Campanha desconhecida")
    return cfg
