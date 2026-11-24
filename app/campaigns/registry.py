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

Páginas de oferta (www.impacta.com.br/ofertas/<oferta>) + RD Station Marketing
------------------------------------------------------------------------------
Além do negócio no RD CRM, uma campanha pode registrar uma **conversão** no RD
Marketing (serviço `app/services/rd_marketing.py`). Um fluxo de automação do RD
Marketing com entrada "conversão `oferta-<oferta>`" manda o e-mail de
agradecimento e chama o webhook do RD Conversas (template de WhatsApp + fila).

Chaves opcionais por campanha:
  - "oferta":       código estável da oferta, igual ao caminho da página
                    (ex.: "formacao-excel"). Não muda de turma para turma.
  - "rd_marketing": {"conversion_identifier": "oferta-<oferta>[-empresa]",
                     "tags": ["oferta-<oferta>", ...]}  (tags em minúsculas)
                    Sem este bloco a conversão NÃO é enviada (LPs antigas,
                    como as do Curso Claude, continuam iguais).

Para cadastrar uma oferta nova (ex.: Power BI), copie as duas entradas do Excel:

    "formacao-power-bi": {
        "oferta": "formacao-power-bi",
        "product_label": "Formação Power BI",
        "funnel_id":     "6487550c634ed10022505f19",  # B2C - Treinamentos
        "deal_stage_id": "6487550c634ed10022505f1a",  # Aguardando atendimento
        "deal_name_tpl": "LP - Formação Power BI [{channel_label}] — {name}",
        "tags": ["origem:LP-Formacao-Power-BI", "lp:formacao-power-bi",
                 "oferta:formacao-power-bi"],
        "custom_fields": {},
        "rd_marketing": {
            "conversion_identifier": "oferta-formacao-power-bi",
            "tags": ["oferta-formacao-power-bi"],
        },
    },
    "formacao-power-bi-empresa": {  # "É para minha empresa" → B2B - Corporativo
        "oferta": "formacao-power-bi",
        ...  # funnel_id/deal_stage_id do B2B, como em formacao-excel-empresa
        "rd_marketing": {
            "conversion_identifier": "oferta-formacao-power-bi-empresa",
            "tags": ["oferta-formacao-power-bi", "b2b"],
        },
    },

e no RD Marketing crie o fluxo de automação com entrada nas conversões
`oferta-formacao-power-bi` e `oferta-formacao-power-bi-empresa`.
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
    # Lançamento Julho/2026 da Formação Claude Pro (Turma 2 — clone da de maio).
    # A LP (tracking-config.json) passou a enviar este slug; sem esta entrada
    # /api/leads retornaria 404 "Campanha desconhecida" e os leads parariam.
    # Mesmo funil/etapa da maio — só muda a tag de campanha pra vendas filtrar.
    "claude-pro-julho-2026": {
        "product_label": "Curso Claude Pro",
        "funnel_id":     "6487550c634ed10022505f19",  # "B2C - Treinamentos"
        "deal_stage_id": "6487550c634ed10022505f1a",  # "Aguardando atendimento"
        "deal_name_tpl": "LP - Curso Claude [{channel_label}] — {name}",
        "tags":          [
            "origem:LP-Curso-Claude",
            "lp:claude-pro",
            "campanha:julho-2026",
        ],
        "custom_fields": {},
    },
    # Turma 3 (Agosto/2026) da Formação Claude Pro — remarcação (início 03/08/2026).
    # LEGADO: turma encerrada; mantida para leads em voo não caírem em 404.
    # Mesmo funil/etapa das anteriores — só muda a tag de campanha.
    "claude-pro-agosto-2026": {
        "product_label": "Curso Claude Pro",
        "funnel_id":     "6487550c634ed10022505f19",  # "B2C - Treinamentos"
        "deal_stage_id": "6487550c634ed10022505f1a",  # "Aguardando atendimento"
        "deal_name_tpl": "LP - Curso Claude [{channel_label}] — {name}",
        "tags":          [
            "origem:LP-Curso-Claude",
            "lp:claude-pro",
            "campanha:agosto-2026",
        ],
        "custom_fields": {},
    },
    # Lançamento Setembro/2026 da Formação Claude Pro (Turma 4, 14–18/09).
    # Mesmo funil/etapa das turmas anteriores — só muda a tag de campanha.
    "claude-pro-setembro-2026": {
        "product_label": "Curso Claude Pro",
        "funnel_id":     "6487550c634ed10022505f19",  # "B2C - Treinamentos"
        "deal_stage_id": "6487550c634ed10022505f1a",  # "Aguardando atendimento"
        "deal_name_tpl": "LP - Curso Claude [{channel_label}] — {name}",
        "tags":          [
            "origem:LP-Curso-Claude",
            "lp:claude-pro",
            "campanha:setembro-2026",
        ],
        "custom_fields": {},
    },
    # Lançamento Outubro/2026 da Formação Claude Pro (Turma 5, 19–23/10).
    # Mesmo funil/etapa das turmas anteriores — só muda a tag de campanha.
    "claude-pro-outubro-2026": {
        "product_label": "Curso Claude Pro",
        "funnel_id":     "6487550c634ed10022505f19",  # "B2C - Treinamentos"
        "deal_stage_id": "6487550c634ed10022505f1a",  # "Aguardando atendimento"
        "deal_name_tpl": "LP - Curso Claude [{channel_label}] — {name}",
        "tags":          [
            "origem:LP-Curso-Claude",
            "lp:claude-pro",
            "campanha:outubro-2026",
        ],
        "custom_fields": {},
    },
    # Lançamento Novembro/2026 da Formação Claude Pro (Turma 6, 23–27/11).
    # Nova vaga Engaged (irihaohzhc), turma_id 175459. Mesmo funil/etapa.
    "claude-pro-novembro-2026": {
        "product_label": "Curso Claude Pro",
        "funnel_id":     "6487550c634ed10022505f19",  # "B2C - Treinamentos"
        "deal_stage_id": "6487550c634ed10022505f1a",  # "Aguardando atendimento"
        "deal_name_tpl": "LP - Curso Claude [{channel_label}] — {name}",
        "tags":          [
            "origem:LP-Curso-Claude",
            "lp:claude-pro",
            "campanha:novembro-2026",
        ],
        "custom_fields": {},
    },
    # Lançamento Junho/2026 do Código Zero (Python, IA e Automação p/ Não Programadores)
    # LEGADO: turma remarcada para 03/08/2026 — a LP agora envia
    # "codigozero-agosto-2026". Entrada mantida por compat com leads em voo.
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
    # Turma Agosto/2026 do Código Zero (remarcação da de junho — início 03/08/2026).
    # LEGADO: turma remarcada de novo para 28/09/2026 — a LP agora envia
    # "codigozero-setembro-2026". Entrada mantida por compat com leads em voo.
    "codigozero-agosto-2026": {
        "product_label": "Código Zero",
        "funnel_id":     "6487550c634ed10022505f19",  # "B2C - Treinamentos"
        "deal_stage_id": "6487550c634ed10022505f1a",  # "Aguardando atendimento"
        "deal_name_tpl": "LP - Código Zero [{channel_label}] — {name}",
        "tags":          [
            "origem:LP-Codigo-Zero",
            "lp:codigozero",
            "campanha:agosto-2026",
        ],
        "custom_fields": {},
    },
    # Turma Setembro/2026 do Código Zero (remarcação da de agosto — início 28/09/2026).
    # A LP (index.html) passou a enviar este slug; sem esta entrada /api/leads
    # retornaria 404 "Campanha desconhecida" e os leads parariam. Mesmo funil/etapa
    # das anteriores — só muda a tag de campanha pra vendas filtrar.
    "codigozero-setembro-2026": {
        "product_label": "Código Zero",
        "funnel_id":     "6487550c634ed10022505f19",  # "B2C - Treinamentos"
        "deal_stage_id": "6487550c634ed10022505f1a",  # "Aguardando atendimento"
        "deal_name_tpl": "LP - Código Zero [{channel_label}] — {name}",
        "tags":          [
            "origem:LP-Codigo-Zero",
            "lp:codigozero",
            "campanha:setembro-2026",
        ],
        "custom_fields": {},
    },
    # Lançamento Junho/2026 do ADV-IA (Inteligência Artificial aplicada ao Direito)
    "advia-junho-2026": {
        "product_label": "ADV-IA",
        # Reaproveita o funil "B2C - Treinamentos". Vendas pode apontar um
        # funil/etapa dedicados — basta trocar os dois IDs abaixo.
        "funnel_id":     "6487550c634ed10022505f19",  # "B2C - Treinamentos"
        "deal_stage_id": "6487550c634ed10022505f1a",  # "Aguardando atendimento"
        "deal_name_tpl": "LP - ADV-IA [{channel_label}] — {name}",
        "tags":          [
            "origem:LP-ADV-IA",
            "lp:advia",
            "campanha:junho-2026",
            "publico:advogados",
        ],
        "custom_fields": {},
    },
    # Hub Corporativo (B2B) — corporate.technowhub.ai / impacta.com.br/corporate.
    # "Igual ao Claude": reaproveita o funil "B2C - Treinamentos". Pra um funil
    # B2B dedicado, troque só os 2 IDs (funnel_id + deal_stage_id) abaixo.
    "corporativo": {
        "product_label": "Corporativo",
        "funnel_id":     "6894b0eb767596001722fd1f",  # "B2B - Corporativo"
        "deal_stage_id": "6894b0eb767596001722fd21",  # "Aguardando Atendimento" (etapa de entrada)
        "deal_name_tpl": "LP - Corporativo [{channel_label}] — {name}",
        "tags":          [
            "origem:LP-Corporativo",
            "lp:corporativo",
            "b2b",
        ],
        "custom_fields": {},
    },
    # Páginas de oferta da Tech Now (www.impacta.com.br/ofertas/<nome>).
    # Um código por OFERTA, sem mês/turma: a turma escolhida vai nos dados do
    # negócio e o vendedor trata no funil. "-empresa" = "É para minha empresa"
    # no formulário → funil B2B - Corporativo.
    "formacao-excel": {
        "oferta":        "formacao-excel",
        "product_label": "Formação Excel com IA e Copilot",
        "funnel_id":     "6487550c634ed10022505f19",  # "B2C - Treinamentos"
        "deal_stage_id": "6487550c634ed10022505f1a",  # "Aguardando atendimento"
        "deal_name_tpl": "LP - Formação Excel [{channel_label}] — {name}",
        "tags":          [
            "origem:LP-Formacao-Excel",
            "lp:formacao-excel",
            "oferta:formacao-excel",
        ],
        "custom_fields": {},
        # Conversão no RD Marketing → e-mail de agradecimento + WhatsApp (RD Conversas).
        "rd_marketing": {
            "conversion_identifier": "oferta-formacao-excel",
            "tags": ["oferta-formacao-excel"],
        },
    },
    "formacao-excel-empresa": {
        "oferta":        "formacao-excel",
        "product_label": "Formação Excel com IA e Copilot (empresa)",
        "funnel_id":     "6894b0eb767596001722fd1f",  # "B2B - Corporativo"
        "deal_stage_id": "6894b0eb767596001722fd21",  # "Aguardando Atendimento"
        "deal_name_tpl": "LP - Formação Excel · Empresa [{channel_label}] — {name}",
        "tags":          [
            "origem:LP-Formacao-Excel",
            "lp:formacao-excel",
            "oferta:formacao-excel",
            "b2b",
        ],
        "custom_fields": {},
        "rd_marketing": {
            "conversion_identifier": "oferta-formacao-excel-empresa",
            "tags": ["oferta-formacao-excel", "b2b"],
        },
    },
    # Página de IA Corporativa — ia-corporate / impacta.com.br/ia-corporate.
    "corporativo-ia": {
        "product_label": "IA Corporativa",
        "funnel_id":     "6894b0eb767596001722fd1f",  # "B2B - Corporativo" (mesmo do hub)
        "deal_stage_id": "6894b0eb767596001722fd21",  # "Aguardando Atendimento" (etapa de entrada)
        "deal_name_tpl": "LP - IA Corporativa [{channel_label}] — {name}",
        "tags":          [
            "origem:LP-IA-Corporativa",
            "lp:corporativo-ia",
            "b2b",
            "tema:ia",
        ],
        "custom_fields": {},
    },
}


def get_campaign(slug: str) -> Optional[CampaignConfig]:
    return CAMPAIGNS.get(slug)
