#!/usr/bin/env bash
# Descobre funnel_id (deal_pipeline_id) e deal_stage_id do RD CRM.
# Use o token API obtido em Avatar -> Integrações -> Token API.
#
# Uso:
#   RD_CRM_TOKEN=seu_token ./scripts/discover-rd-ids.sh
#
# Ou:
#   ./scripts/discover-rd-ids.sh seu_token

set -euo pipefail

TOKEN="${RD_CRM_TOKEN:-${1:-}}"
if [ -z "$TOKEN" ]; then
  echo "Uso: RD_CRM_TOKEN=... $0   ou   $0 <token>" >&2
  exit 1
fi

BASE="https://crm.rdstation.com/api/v1"

echo "═══════════════════════════════════════════════════════════════"
echo "  PIPELINES (funis) disponíveis"
echo "═══════════════════════════════════════════════════════════════"
curl -sf "$BASE/deal_pipelines?token=$TOKEN" \
  | python3 -c "
import sys, json
data = json.load(sys.stdin)
items = data if isinstance(data, list) else data.get('deal_pipelines', [])
for p in items:
    pid = p.get('_id') or p.get('id')
    name = p.get('name', '?')
    print(f'  {pid}  →  {name}')
"

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  STAGES (etapas) — agrupadas por pipeline"
echo "═══════════════════════════════════════════════════════════════"
curl -sf "$BASE/deal_stages?token=$TOKEN" \
  | python3 -c "
import sys, json
data = json.load(sys.stdin)
items = data if isinstance(data, list) else data.get('deal_stages', [])
by_pipeline = {}
for s in items:
    pid = s.get('deal_pipeline_id', '?')
    by_pipeline.setdefault(pid, []).append(s)
for pid, stages in by_pipeline.items():
    print(f'  Pipeline: {pid}')
    for s in stages:
        sid = s.get('_id') or s.get('id')
        nome = s.get('name', '?')
        print(f'    {sid}  →  {nome}')
"

echo ""
echo "Próximo passo: copie o funnel_id e o deal_stage_id corretos para"
echo "  app/campaigns/registry.py (campos TODO_funnel_id e TODO_deal_stage_id)"
echo "depois faça commit + push (Coolify redeploya automaticamente)."
