from pydantic_settings import BaseSettings, SettingsConfigDict


# Origens SEMPRE liberadas (LPs da Impacta), independente do env. Evita o CORS
# bloquear o /api/leads quando a LP roda nesses domínios.
_BASELINE_ORIGINS = [
    "https://corporate.technowhub.ai",
    "https://ia-corporate.technowhub.ai",
    "https://www.impacta.com.br",
    # Origem das páginas de oferta (Cloudflare Pages), servidas em
    # www.impacta.com.br/ofertas/ por proxy; a origem também é testada direto.
    "https://ofertas.technowhub.ai",
    "https://impacta.com.br",
    # LP do Curso Claude (domínio público); a origem claude.technowhub.ai vem do env.
    "https://claude.impacta.com.br",
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    rd_crm_token: str = ""
    iris_webhook_url: str = ""
    iris_webhook_secret: str = ""
    allowed_origins: str = "http://localhost:3000"
    log_level: str = "INFO"
    # Meta CAPI: pra enviar eventos server-side para o Pixel.
    # Deixar vazio se nao quer usar CAPI (LP usa apenas Pixel client-side).
    meta_pixel_id: str = ""
    meta_capi_token: str = ""
    # RD Station Marketing — API de conversões (token público). Vazio = o passo
    # de conversão vira no-op com log (deploy seguro antes do token existir).
    rdsm_api_key: str = ""
    # Base legal enviada em legal_bases (categoria "communications").
    rdsm_legal_basis_type: str = "pre_existent_contract"
    # Campos personalizados (cf_*) que podem ser enviados — CSV. Só liste campos
    # que JÁ existem no RD Marketing; campo inexistente pode fazer o RD recusar.
    # Suportados: cf_oferta_curso, cf_oferta_modalidade, cf_oferta_turma, cf_oferta_link.
    rdsm_custom_fields: str = ""

    @property
    def rdsm_custom_fields_list(self) -> list[str]:
        return [c.strip() for c in self.rdsm_custom_fields.split(",") if c.strip()]

    @property
    def allowed_origins_list(self) -> list[str]:
        env = [o.strip() for o in self.allowed_origins.split(",") if o.strip()]
        # une env + baseline, deduplicando e preservando ordem
        return list(dict.fromkeys(env + _BASELINE_ORIGINS))


settings = Settings()
