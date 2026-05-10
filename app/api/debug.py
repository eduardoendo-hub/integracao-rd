"""
Rotas de debug para inspecionar diretamente o estado dos objetos no RD CRM.
Usa o token configurado no servidor — nao expoe credenciais ao cliente.

NUNCA expor publicamente em produção sem proteção. Como esta API roda
internamente entre LP/IRIS/operador, mantemos sem auth no MVP — proteger
no Coolify (ALLOWED_ORIGINS) ou via reverse proxy se for ficar exposto.
"""

import logging
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException

from app.core.config import settings
from app.services import rd_crm

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/debug/deals/{deal_id}")
async def get_deal_debug(deal_id: str) -> dict:
    """Retorna o JSON completo de um Deal no RD CRM (incluindo contatos vinculados)."""
    if not settings.rd_crm_token:
        raise HTTPException(status_code=500, detail="RD_CRM_TOKEN ausente")
    async with httpx.AsyncClient(timeout=15) as client:
        deal = await rd_crm.get_deal(client, deal_id)
        if not deal:
            raise HTTPException(status_code=404, detail=f"Deal {deal_id} nao encontrado")
        return deal


@router.get("/debug/contacts/{contact_id}")
async def get_contact_debug(contact_id: str) -> dict:
    """Retorna o JSON completo de um Contato no RD CRM."""
    if not settings.rd_crm_token:
        raise HTTPException(status_code=500, detail="RD_CRM_TOKEN ausente")
    base = "https://crm.rdstation.com/api/v1"
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            r = await client.get(f"{base}/contacts/{contact_id}", params={"token": settings.rd_crm_token})
            if r.status_code != 200:
                raise HTTPException(status_code=r.status_code, detail=r.text[:300])
            return r.json()
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("[debug] erro ao buscar contato")
            raise HTTPException(status_code=500, detail=str(e))
