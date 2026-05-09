"""
Registro de campanhas reconhecidas pelo serviço.

Cada entrada mapeia um `campaign_slug` (vindo do payload do Lead) para a configuração
RD CRM correspondente: pipeline (funil), etapa inicial, template do nome do deal e
custom fields a aplicar.

Os IDs de pipeline e stage podem ser descobertos com:

    curl "https://crm.rdstation.com/api/v1/deal_pipelines?token=$RD_CRM_TOKEN"
    curl "https://crm.rdstation.com/api/v1/deal_stages?token=$RD_CRM_TOKEN"

Quando uma nova LP entrar no ar, basta adicionar uma entrada aqui — sem alterar código
de serviço.
"""

from typing import Optional

CampaignConfig = dict


CAMPAIGNS: dict[str, CampaignConfig] = {
    # Lançamento Maio/2026 da Formação Claude Pro
    "claude-pro-maio-2026": {
        "funnel_id":     "TODO_funnel_id",        # preencher com ID do funil "Curso Claude Pro" no RD CRM
        "deal_stage_id": "TODO_deal_stage_id",    # preencher com ID da etapa "Lead novo"
        "deal_name_tpl": "Curso Claude Pro — {name}",
        "tags":          ["lp:claude-pro", "campanha:maio-2026"],
        # Custom fields aplicados ao deal no momento de criação.
        # Os placeholders {field} são interpolados com dados do payload (utm.x, perfil, extras).
        "custom_fields": {
            "cf_campanha":     "Claude Pro Maio 2026",
            "cf_perfil":       "{perfil}",
            "cf_utm_source":   "{utm.source}",
            "cf_utm_medium":   "{utm.medium}",
            "cf_utm_campaign": "{utm.campaign}",
            "cf_utm_content":  "{utm.content}",
            "cf_source_page":  "{source_page}",
        },
    },
}


def get_campaign(slug: str) -> Optional[CampaignConfig]:
    return CAMPAIGNS.get(slug)
