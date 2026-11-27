"""Fonte e Campanha do negócio: vão no POST /deals e, se o RD não gravar, num PUT."""
import asyncio
import json

import httpx

from app.campaigns.registry import get_campaign
from app.services import rd_crm

FONTE = "6b099eeb48755b0022513d17"
CAMP_EXCEL = "6b099eec12453d001d538055"
CAMP_PBI = "6b099eec65144b001f8904f1"


def _gravador(resposta_post):
    chamadas = []

    def handler(req: httpx.Request):
        corpo = json.loads(req.content or b"{}")
        chamadas.append((req.method, req.url.path, corpo))
        if req.method == "POST":
            return httpx.Response(201, json=resposta_post)
        return httpx.Response(200, json={})

    return chamadas, httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_post_leva_fonte_e_campanha_top_level():
    chamadas, cli = _gravador({"_id": "d1"})

    async def go():
        async with cli as c:
            await rd_crm.create_deal(c, deal_name="x", contact_id="c1", deal_stage_id="s1",
                                     deal_source_id=FONTE, campaign_id=CAMP_EXCEL)
    asyncio.run(go())
    _, _, corpo = chamadas[0]
    assert corpo["deal_source"] == {"_id": FONTE}
    assert corpo["campaign"] == {"_id": CAMP_EXCEL}


def test_sem_ids_nao_manda_nada():
    chamadas, cli = _gravador({"_id": "d1"})

    async def go():
        async with cli as c:
            await rd_crm.create_deal(c, deal_name="x", contact_id="c1", deal_stage_id="s1")
    asyncio.run(go())
    _, _, corpo = chamadas[0]
    assert "deal_source" not in corpo and "campaign" not in corpo


def test_put_quando_o_post_nao_gravou():
    chamadas, cli = _gravador({})

    async def go():
        async with cli as c:
            await rd_crm.set_deal_source_and_campaign(c, deal_id="d1", deal_envelope={"_id": "d1"},
                                                      deal_source_id=FONTE, campaign_id=CAMP_PBI)
    asyncio.run(go())
    metodo, caminho, corpo = chamadas[0]
    assert metodo == "PUT" and caminho.endswith("/deals/d1")
    assert corpo["deal_source"] == {"_id": FONTE} and corpo["campaign"] == {"_id": CAMP_PBI}


def test_sem_put_quando_o_post_ja_gravou():
    chamadas, cli = _gravador({})
    env = {"_id": "d1", "deal_source": {"_id": FONTE, "name": "x"}, "campaign": {"_id": CAMP_PBI}}

    async def go():
        async with cli as c:
            await rd_crm.set_deal_source_and_campaign(c, deal_id="d1", deal_envelope=env,
                                                      deal_source_id=FONTE, campaign_id=CAMP_PBI)
    asyncio.run(go())
    assert chamadas == []


def test_ofertas_tem_fonte_e_campanha():
    for slug, camp in (("formacao-excel", CAMP_EXCEL), ("formacao-excel-empresa", CAMP_EXCEL),
                       ("formacao-power-bi", CAMP_PBI), ("formacao-power-bi-empresa", CAMP_PBI)):
        cfg = get_campaign(slug)
        assert cfg["rd_source_id"] == FONTE
        assert cfg["rd_campaign_id"] == camp
    # LPs antigas não mudam
    assert "rd_source_id" not in get_campaign("claude-pro-maio-2026")
