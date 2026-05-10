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
echo "  STAGES (etapas) — uma chamada por pipeline"
echo "═══════════════════════════════════════════════════════════════"
# A API /deal_stages SEM filtro retorna stages de apenas UM pipeline
# (default). Iteramos sobre cada pipeline e buscamos suas stages
# especificamente via ?deal_pipeline_id=
PIPELINE_LIST=$(curl -sf "$BASE/deal_pipelines?token=$TOKEN" \
  | python3 -c "
import sys, json
data = json.load(sys.stdin)
items = data if isinstance(data, list) else data.get('deal_pipelines', [])
for p in items:
    pid = p.get('_id') or p.get('id')
    name = p.get('name', '?')
    print(pid + '|' + name)
")

while IFS='|' read -r PID PNAME; do
  [ -z "$PID" ] && continue
  echo ""
  echo "  ─── $PNAME"
  echo "      pipeline_id: $PID"
  curl -sf "$BASE/deal_stages?token=$TOKEN&deal_pipeline_id=$PID" \
    | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    items = data if isinstance(data, list) else data.get('deal_stages', [])
    if not items:
        print('      (sem stages)')
    for s in items:
        sid = s.get('_id') or s.get('id')
        nome = s.get('name', '?')
        print(f'      {sid}  →  {nome}')
except Exception as e:
    print(f'      (erro: {e})')
"
done <<< "$PIPELINE_LIST"

echo ""
echo "Próximo passo: copie o funnel_id e o deal_stage_id corretos para"
echo "  app/campaigns/registry.py (campos TODO_funnel_id e TODO_deal_stage_id)"
echo "depois faça commit + push (Coolify redeploya automaticamente)."
