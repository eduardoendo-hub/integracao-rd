from pydantic_settings import BaseSettings, SettingsConfigDict


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

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


settings = Settings()
