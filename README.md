# integracao-rd

Microserviço HTTP reutilizável que recebe leads de qualquer landing page da Impacta e cria
**Contact + Deal** no funil correto do **RD CRM** (vendas), retornando o `deal_id`. Encaminha
um webhook ao **IRIS** para alimentar o dashboard real-time.

Uma instância serve **todas as LPs** — a campanha de destino é selecionada por `campaign_slug`
no body da requisição, com configuração por campanha em `app/campaigns/registry.py`.

## Stack

- Python 3.12 · FastAPI · httpx async · Pydantic v2
- Deploy via container Docker no Coolify (subdomínio sugerido: `rd.impacta.com.br`)

## Endpoints

| Método | Path | Descrição |
|---|---|---|
| POST | `/api/leads` | Cria/atualiza Contact + Deal no RD CRM. Encaminha evento ao IRIS. |
| POST | `/api/leads/whatsapp-click` | Registra clique em WhatsApp (sem criar deal). Encaminha ao IRIS. |
| GET | `/api/campaigns/{slug}` | Devolve a config de uma campanha (debug). |
| GET | `/api/healthz` | Healthcheck para o Coolify. |

### POST /api/leads — payload

```json
{
  "campaign_slug": "claude-pro-maio-2026",
  "name": "Maria Silva",
  "email": "maria@empresa.com",
  "phone": "+55 11 99999-9999",
  "perfil": "Gestora",
  "utm": {
    "source": "meta",
    "medium": "cpc",
    "campaign": "prospecting",
    "content": "reel_20projetos"
  },
  "source_page": "https://impacta.com.br/claude",
  "extra": { "empresa": "Acme", "cargo": "Head Marketing" }
}
```

Resposta:

```json
{
  "deal_id":    "abc123…",
  "contact_id": "xyz789…",
  "status":     "created"
}
```

## Configuração de campanhas

`app/campaigns/registry.py` — dict simples Python. Cada entrada precisa de `funnel_id` e
`deal_stage_id` válidos (ex.: etapa "Lead novo"). Para descobrir os IDs disponíveis:

```bash
curl "https://crm.rdstation.com/api/v1/deal_pipelines?token=$RD_CRM_TOKEN"
curl "https://crm.rdstation.com/api/v1/deal_stages?token=$RD_CRM_TOKEN"
```

## Variáveis de ambiente

Veja `.env.example`. Mínimo para rodar:

| Var | Obrigatória | Descrição |
|---|---|---|
| `RD_CRM_TOKEN` | sim | Token API do RD CRM (Avatar → Integrações → Token API) |
| `IRIS_WEBHOOK_URL` | não | Base URL do IRIS (sem trailing slash) — ex. `https://iris.technowhub.ai`. O serviço POSTa em `${IRIS_WEBHOOK_URL}/api/webhook/rd`. |
| `IRIS_WEBHOOK_SECRET` | não | Segredo HMAC compartilhado com o IRIS |
| `ALLOWED_ORIGINS` | sim | Lista CSV de origens CORS — ex. `https://impacta.com.br,https://www.impacta.com.br` |
| `LOG_LEVEL` | não | `INFO` (default) · `DEBUG` para troubleshooting |

## Rodar localmente

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # editar com seus valores
uvicorn app.main:app --reload --port 8000
```

Testar:

```bash
curl -X POST http://localhost:8000/api/leads \
  -H 'Content-Type: application/json' \
  -d '{
    "campaign_slug": "claude-pro-maio-2026",
    "name": "Teste Local",
    "email": "teste@local.com",
    "phone": "+55 11 99999-9999",
    "perfil": "Gestora"
  }'
```

## Deploy no Coolify

1. Criar nova aplicação Docker → apontar para o repo Git deste projeto.
2. Build pack: **Dockerfile** (na raiz do repo — Coolify acha automaticamente).
3. Configurar env vars na UI do Coolify.
4. Domínio: `rd.impacta.com.br` (HTTPS automático via Coolify/Traefik).
5. Healthcheck: `GET /api/healthz`.
6. Port: `8000`.

## Padrão de referência

Este serviço porta padrões de `~/Documents/Claude/Projects/BOT-SDR-PJ/app/services/rd_crm.py`
(httpx async, token como query param, normalização de telefone). Adiciona endpoints HTTP
genéricos (a referência só faz **leitura** do CRM — este serviço também **escreve**).
