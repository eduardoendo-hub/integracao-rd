"""Busca de contato no RD CRM: só aceita contato que tem de fato o e-mail/telefone."""
import asyncio

import httpx

from app.services import rd_crm

EDU_ANTIGO = {"_id": "a", "emails": [{"email": "edu@x.com"}], "phones": [{"phone": "+55 (11) 9 8456-1270"}]}
EDU_DUP = {"_id": "b", "emails": [{"email": "edu@x.com"}], "phones": [{"phone": "5511999990000"}]}
JOAO = {"_id": "c", "emails": [{"email": "joao@x.com"}], "phones": [{"phone": "5511984561270"}]}
SEM_EMAIL = {"_id": "d", "emails": [], "phones": [{"phone": "11984561270"}]}


def _client(contacts):
    """API que ignora o filtro e devolve sempre a lista toda (pior caso do v1)."""
    return httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"contacts": contacts})))


def run(coro):
    return asyncio.run(coro)


async def _email(contacts, email, phone=None):
    async with _client(contacts) as c:
        return await rd_crm.find_contact_by_email(c, email, phone)


async def _phone(contacts, phone, email=None):
    async with _client(contacts) as c:
        return await rd_crm.find_contact_by_phone(c, phone, email)


def test_email_ignora_resultado_fora_do_filtro():
    assert run(_email([JOAO], "edu@x.com")) is None


def test_email_prefere_o_que_tem_o_telefone():
    assert run(_email([EDU_DUP, EDU_ANTIGO], "EDU@x.com", "11984561270"))["_id"] == "a"


def test_telefone_nao_casa_com_contato_de_outro_email():
    assert run(_phone([JOAO], "11984561270", "edu@x.com")) is None


def test_telefone_aceita_contato_sem_email():
    assert run(_phone([JOAO, SEM_EMAIL], "11984561270", "edu@x.com"))["_id"] == "d"


def test_telefone_sem_email_no_lead_aceita_qualquer_match():
    assert run(_phone([EDU_DUP, JOAO], "(11) 98456-1270"))["_id"] == "c"


def test_telefone_ignora_resultado_fora_do_filtro():
    assert run(_phone([EDU_DUP], "11984561270")) is None
