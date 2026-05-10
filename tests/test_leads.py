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
