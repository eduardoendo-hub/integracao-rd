"""
Smoke tests do endpoint /api/leads.

Não chamam o RD CRM real — apenas validam o contrato HTTP do serviço (404 para campanha
desconhecida, 422 para payload inválido). Para testar a criação real de Deal no RD CRM,
use o curl do README.md com RD_CRM_TOKEN configurado.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_healthz():
    r = client.get("/api/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_lead_unknown_campaign():
    r = client.post("/api/leads", json={
        "campaign_slug": "campanha-inexistente",
        "name": "Teste",
        "email": "teste@x.com",
    })
    assert r.status_code == 404


def test_lead_missing_email_and_phone():
    r = client.post("/api/leads", json={
        "campaign_slug": "claude-pro-maio-2026",
        "name": "Teste",
    })
    assert r.status_code == 422  # Pydantic validation


def test_get_campaign_config():
    r = client.get("/api/campaigns/claude-pro-maio-2026")
    assert r.status_code == 200
    data = r.json()
    assert "funnel_id" in data
    assert "deal_stage_id" in data
    assert "{name}" in data["deal_name_tpl"]
    assert "LP - Curso Claude" in data["deal_name_tpl"]
    assert "origem:LP-Curso-Claude" in data.get("tags", [])


def test_get_unknown_campaign_404():
    r = client.get("/api/campaigns/nao-existe")
    assert r.status_code == 404


def test_formacao_excel_campaigns():
    """Ofertas da Tech Now: um código por oferta, sem mês; empresa vai pro B2B."""
    pessoa = client.get("/api/campaigns/formacao-excel").json()
    empresa = client.get("/api/campaigns/formacao-excel-empresa").json()
    assert pessoa["funnel_id"] == "6487550c634ed10022505f19"   # B2C - Treinamentos
    assert empresa["funnel_id"] == "6894b0eb767596001722fd1f"  # B2B - Corporativo
    assert "oferta:formacao-excel" in pessoa["tags"]
    assert "b2b" in empresa["tags"]


def test_cors_ofertas_origin():
    r = client.options("/api/leads", headers={
        "Origin": "https://ofertas.technowhub.ai",
        "Access-Control-Request-Method": "POST",
    })
    assert r.headers.get("access-control-allow-origin") == "https://ofertas.technowhub.ai"


def test_description_groups_extra():
    from app.api.leads import _build_lead_description
    from app.models.lead import LeadIn
    lead = LeadIn(campaign_slug="formacao-excel", name="Teste", email="t@x.com", channel="form",
                  extra={"produto": "Formação Excel", "modalidade": "online", "turma_descricao": "Módulo I · Online · 05/12",
                         "gclid": "abc", "campo_novo": "x", "vazio": ""})
    d = _build_lead_description(lead, {"product_label": "Formação Excel"})
    assert "INTERESSE" in d and "Turma escolhida: Módulo I · Online · 05/12" in d
    assert "RASTREAMENTO" in d and "gclid (Google Ads): abc" in d
    assert "OUTROS DADOS" in d and "campo_novo: x" in d
    assert "vazio" not in d
