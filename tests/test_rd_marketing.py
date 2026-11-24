"""
Testes da conversão no RD Station Marketing (app/services/rd_marketing.py).

Nenhuma requisição real: o transporte HTTP é um httpx.MockTransport e o RD CRM
é substituído por um falso. O token usado é fictício.
"""

import asyncio
import json
import logging

import httpx
import pytest
from fastapi.testclient import TestClient

from app.campaigns.registry import get_campaign
from app.core.config import settings
from app.main import app
from app.models.lead import LeadIn
from app.services import rd_crm, rd_marketing

FAKE_KEY = "token-ficticio-de-teste"

LEAD_JSON = {
    "campaign_slug": "formacao-excel",
    "name": "Maria Teste",
    "email": "maria.teste@example.com",
    "phone": "(11) 98765-4321",
    "utm": {"source": "google", "medium": "cpc", "campaign": "excel-search", "term": "curso excel"},
    "source_page": "https://www.impacta.com.br/ofertas/formacao-excel",
    "extra": {
        "produto": "Formação Excel com IA e Copilot",
        "modalidade": "online",
        "turma_descricao": "Módulo I · Online · 05/12",
        "landing_page": "https://www.impacta.com.br/ofertas/formacao-excel",
    },
}


class Recorder:
    """MockTransport que guarda as requisições e devolve respostas em sequência."""

    def __init__(self, *responses):
        self.requests: list[httpx.Request] = []
        self.responses = list(responses) or [httpx.Response(200, json={"event_uuid": "x"})]

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        resp = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(resp, Exception):
            raise resp
        return resp

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)


@pytest.fixture
def rec(monkeypatch):
    r = Recorder()
    monkeypatch.setattr(rd_marketing, "_transport", r.transport)
    monkeypatch.setattr(rd_marketing, "_RETRY_DELAY", 0)
    monkeypatch.setattr(settings, "rdsm_api_key", FAKE_KEY)
    monkeypatch.setattr(settings, "rdsm_custom_fields", "")
    return r


@pytest.fixture
def fake_crm(monkeypatch):
    async def fake_upsert(**kwargs):
        return {"contact_id": "c1", "deal_id": "d1", "status": "created"}
    monkeypatch.setattr(rd_crm, "upsert_contact_and_create_deal", fake_upsert)


def _send(slug: str = "formacao-excel", **overrides) -> bool:
    lead = LeadIn(**{**LEAD_JSON, "campaign_slug": slug, **overrides})
    return asyncio.run(rd_marketing.send_conversion(lead, get_campaign(slug)))


def test_envia_conversao_com_bloco(rec):
    assert _send() is True
    assert len(rec.requests) == 1
    req = rec.requests[0]
    assert req.method == "POST"
    assert req.url.host == "api.rd.services"
    assert req.url.path == "/platform/conversions"
    assert req.url.params["api_key"] == FAKE_KEY
    body = json.loads(req.content)
    assert body["event_type"] == "CONVERSION"
    assert body["event_family"] == "CDP"
    p = body["payload"]
    assert p["conversion_identifier"] == "oferta-formacao-excel"
    assert p["email"] == "maria.teste@example.com"
    assert p["name"] == "Maria Teste"
    assert p["mobile_phone"] == "+5511987654321"
    assert p["traffic_source"] == "google"
    assert p["traffic_medium"] == "cpc"
    assert p["traffic_campaign"] == "excel-search"
    assert p["traffic_value"] == "curso excel"
    assert p["tags"] == ["oferta-formacao-excel"]
    assert p["available_for_mailing"] is True
    assert p["legal_bases"] == [
        {"category": "communications", "type": "pre_existent_contract", "status": "granted"}
    ]
    # Sem RDSM_CUSTOM_FIELDS, nenhum cf_* é enviado.
    assert not any(k.startswith("cf_") for k in p)


def test_empresa_usa_conversao_propria(rec):
    assert _send("formacao-excel-empresa") is True
    p = json.loads(rec.requests[0].content)["payload"]
    assert p["conversion_identifier"] == "oferta-formacao-excel-empresa"
    assert p["tags"] == ["oferta-formacao-excel", "b2b"]


def test_campos_personalizados_so_se_permitidos(rec, monkeypatch):
    monkeypatch.setattr(settings, "rdsm_custom_fields", "cf_oferta_curso, cf_oferta_turma,cf_oferta_link")
    monkeypatch.setattr(settings, "rdsm_legal_basis_type", "consent")
    assert _send() is True
    p = json.loads(rec.requests[0].content)["payload"]
    assert p["cf_oferta_curso"] == "Formação Excel com IA e Copilot"
    assert p["cf_oferta_turma"] == "Módulo I · Online · 05/12"
    assert p["cf_oferta_link"] == "https://www.impacta.com.br/ofertas/formacao-excel"
    assert "cf_oferta_modalidade" not in p  # fora da lista permitida
    assert p["legal_bases"][0]["type"] == "consent"


def test_nao_envia_sem_bloco(rec):
    assert get_campaign("claude-pro-novembro-2026").get("rd_marketing") is None
    assert _send("claude-pro-novembro-2026") is False
    assert rec.requests == []


def test_nao_envia_sem_token(rec, monkeypatch, caplog):
    monkeypatch.setattr(settings, "rdsm_api_key", "")
    with caplog.at_level(logging.INFO, logger="app.services.rd_marketing"):
        assert _send() is False
    assert rec.requests == []
    assert "RDSM_API_KEY vazio" in caplog.text


def test_nao_envia_sem_email(rec):
    assert _send(email=None) is False
    assert rec.requests == []


@pytest.mark.parametrize("raw,esperado", [
    ("(11) 98765-4321", "+5511987654321"),
    ("11 3456-7890", "+551134567890"),
    ("+55 (21) 99999-0000", "+5521999990000"),
    ("5511987654321", "+5511987654321"),
    ("011 98765-4321", "+5511987654321"),
    ("(55) 99123-4567", "+5555991234567"),  # DDD 55 (RS) sem DDI
    ("12345", None),
    ("", None),
    (None, None),
])
def test_telefone_normalizado(raw, esperado):
    assert rd_marketing.normalize_mobile_phone(raw) == esperado


def test_retentativa_em_5xx(rec):
    rec.responses = [httpx.Response(503), httpx.Response(200, json={})]
    assert _send() is True
    assert len(rec.requests) == 2


def test_retentativa_em_timeout(rec):
    rec.responses = [httpx.ReadTimeout("timeout"), httpx.Response(200, json={})]
    assert _send() is True
    assert len(rec.requests) == 2


def test_sem_retentativa_em_4xx_e_log_sem_dados_pessoais(rec, caplog):
    rec.responses = [httpx.Response(400, json={"errors": {
        "error_type": "INVALID_FIELDS",
        "error_message": "maria.teste@example.com inválido",
    }})]
    with caplog.at_level(logging.INFO, logger="app.services.rd_marketing"):
        assert _send() is False
    assert len(rec.requests) == 1
    assert "status=400" in caplog.text and "campaign=formacao-excel" in caplog.text
    assert "INVALID_FIELDS" in caplog.text
    for sensivel in ("maria.teste@example.com", "98765", FAKE_KEY):
        assert sensivel not in caplog.text


def test_endpoint_envia_conversao_em_segundo_plano(rec, fake_crm):
    r = TestClient(app).post("/api/leads", json=LEAD_JSON)
    assert r.status_code == 200
    assert r.json()["deal_id"] == "d1"
    assert len(rec.requests) == 1
    assert json.loads(rec.requests[0].content)["payload"]["conversion_identifier"] == "oferta-formacao-excel"


def test_endpoint_sem_bloco_nao_envia(rec, fake_crm):
    r = TestClient(app).post("/api/leads", json={**LEAD_JSON, "campaign_slug": "claude-pro-novembro-2026"})
    assert r.status_code == 200
    assert rec.requests == []


@pytest.mark.parametrize("falha", [httpx.Response(500), httpx.ConnectError("sem rede"), RuntimeError("bug")])
def test_falha_do_rd_marketing_nao_afeta_resposta(rec, fake_crm, falha, caplog):
    rec.responses = [falha]
    with caplog.at_level(logging.INFO, logger="app.services.rd_marketing"):
        r = TestClient(app).post("/api/leads", json=LEAD_JSON)
    assert r.status_code == 200
    assert r.json() == {"deal_id": "d1", "contact_id": "c1", "status": "created"}
    assert "campaign=formacao-excel" in caplog.text
    assert "maria.teste@example.com" not in caplog.text
