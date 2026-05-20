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
        "product_label": "Curso Claude Pro",
        "funnel_id":     "6487550c634ed10022505f19",  # "B2C - Treinamentos"
        "deal_stage_id": "6487550c634ed10022505f1a",  # "Aguardando atendimento" (DENTRO do B2C - Treinamentos)
        # Nome do deal no RD CRM. Inclui o canal de origem entre colchetes para
        # vendas distinguir de cara se veio do formulário, do clique no WhatsApp,
        # etc. Placeholders suportados: {name}, {channel_label}, {perfil}, {utm.*}.
        "deal_name_tpl": "LP - Curso Claude [{channel_label}] — {name}",
        # Tags fixas + dinâmica (canal). A tag canal:{channel} é adicionada
        # automaticamente pelo serviço; aqui ficam as fixas + uma de origem
        # legível para vendas filtrar todos os leads dessa campanha.
        "tags":          [
            "origem:LP-Curso-Claude",
            "lp:claude-pro",
            "campanha:maio-2026",
        ],
        # Custom fields ficam vazios por padrão. UTMs e demais metadados vão para o
        # IRIS via webhook (POST /api/webhook/rd) — onde são salvos no model `Lead`
        # e exibidos no painel comercial. Para anexar custom fields ao deal RD CRM:
        #   1. Em RD CRM → Configurações → Campos personalizados → criar campos
        #      (ex.: "UTM Source", "Perfil") e copiar os IDs.
        #   2. Adicionar abaixo no formato {"<custom_field_id>": "{utm.source}"}
        #      (placeholders {field} são interpolados pelo serviço).
        "custom_fields": {},
    },
    # Lançamento Junho/2026 do Código Zero (Python, IA e Automação p/ Não Programadores)
    "codigozero-junho-2026": {
        "product_label": "Código Zero",
        # Reaproveita o funil "B2C - Treinamentos" do Claude Pro. Vendas pode
        # apontar um funil/etapa dedicados — basta trocar os dois IDs abaixo.
        "funnel_id":     "6487550c634ed10022505f19",  # "B2C - Treinamentos"
        "deal_stage_id": "6487550c634ed10022505f1a",  # "Aguardando atendimento"
        "deal_name_tpl": "LP - Código Zero [{channel_label}] — {name}",
        "tags":          [
            "origem:LP-Codigo-Zero",
            "lp:codigozero",
            "campanha:junho-2026",
        ],
        "custom_fields": {},
    },
}


def get_campaign(slug: str) -> Optional[CampaignConfig]:
    return CAMPAIGNS.get(slug)
