from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field, model_validator


class UTM(BaseModel):
    source: Optional[str] = None
    medium: Optional[str] = None
    campaign: Optional[str] = None
    content: Optional[str] = None
    term: Optional[str] = None


class LeadIn(BaseModel):
    campaign_slug: str = Field(..., min_length=2, max_length=128)
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    perfil: Optional[str] = None
    # Canal pelo qual o lead chegou: "form" (form da LP), "whatsapp" (clique
    # no fab WhatsApp), "email" (resposta a email), etc. Resolvido em tags
    # e no nome do deal via {channel} no registry.
    channel: Optional[str] = "form"
    utm: Optional[UTM] = None
    source_page: Optional[str] = None
    extra: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def _need_email_or_phone(self):
        if not (self.email or self.phone):
            raise ValueError("email ou phone obrigatório")
        return self


class LeadOut(BaseModel):
    deal_id: Optional[str] = None
    contact_id: Optional[str] = None
    status: Literal["created", "updated", "skipped"]


class WhatsAppClickIn(BaseModel):
    campaign_slug: str
    phone: Optional[str] = None
    source_page: Optional[str] = None
    utm: Optional[UTM] = None
