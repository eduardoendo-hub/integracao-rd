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
        "funnel_id":     "6487550c634ed10022505f19",  # "B2C - Treinamentos"
        "deal_stage_id": "6487550c634ed10022505f1a",  # "Aguardando atendimento" (DENTRO do B2C - Treinamentos)
        "deal_name_tpl": "Curso Claude Pro — {name}",
        "tags":          ["lp:claude-pro", "campanha:maio-2026"],
        # Custom fields ficam vazios por padrão. UTMs e demais metadados vão para o
        # IRIS via webhook (POST /api/webhook/rd) — onde são salvos no model `Lead`
        # e exibidos no painel comercial. Para anexar custom fields ao deal RD CRM:
        #   1. Em RD CRM → Configurações → Campos personalizados → criar campos
        #      (ex.: "UTM Source", "Perfil") e copiar os IDs.
        #   2. Adicionar abaixo no formato {"<custom_field_id>": "{utm.source}"}
        #      (placeholders {field} são interpolados pelo serviço).
        "custom_fields": {},
    },
}


def get_campaign(slug: str) -> Optional[CampaignConfig]:
    return CAMPAIGNS.get(slug)
