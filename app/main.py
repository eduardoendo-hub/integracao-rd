import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import debug, health, leads
from app.core.config import settings

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)

app = FastAPI(
    title="integracao-rd",
    description="Recebe Leads de qualquer LP Impacta e cria Contact+Deal no RD CRM",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

app.include_router(health.router, prefix="/api")
app.include_router(leads.router, prefix="/api")
app.include_router(debug.router, prefix="/api")
