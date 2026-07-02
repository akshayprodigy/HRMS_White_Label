from typing import List, Union
from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Veliora"
    LOG_LEVEL: str = "INFO"

    # Boot the in-process APScheduler loop on app startup. Keep this on
    # exactly ONE worker (gunicorn -w 1) — N workers means N scheduler
    # loops. The is_running row-lock on ScheduledJob still prevents a
    # job from running twice concurrently, but duplicate loops waste
    # work. Off by default so plain imports/tests never start it.
    ENABLE_SCHEDULER: bool = False
    
    SECRET_KEY: str = "secret-key-change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8  # 8 days
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 30  # 30 days
    
    # BACKEND_CORS_ORIGINS is a JSON-formatted list of strings
    BACKEND_CORS_ORIGINS: List[AnyHttpUrl] = []

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(
        cls, v: Union[str, List[str]]
    ) -> Union[List[str], str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)

    MARIADB_SERVER: str = "db"
    MARIADB_USER: str = "erp_user"
    MARIADB_PASSWORD: str = "erp_password"
    MARIADB_DB: str = "erp_db"
    MARIADB_PORT: int = 3306

    # File uploads (Lead/Opportunity documents)
    LEAD_DOCUMENTS_DIR: str = "/app/uploads/leads"
    # Default: 25 MiB per file
    LEAD_DOCUMENT_MAX_BYTES: int = 25 * 1024 * 1024

    # File uploads (Task completion evidence)
    TASK_COMPLETION_DOCS_DIR: str = "/app/uploads/task-completion"
    TASK_COMPLETION_DOC_MAX_BYTES: int = 25 * 1024 * 1024

    # File uploads (HR Policy documents)
    POLICY_DOCUMENTS_DIR: str = "/app/uploads/policies"
    POLICY_DOCUMENT_MAX_BYTES: int = 25 * 1024 * 1024

    # File uploads (Employee joining documents)
    EMPLOYEE_DOCUMENTS_DIR: str = "/app/uploads/employee-documents"
    EMPLOYEE_DOCUMENT_MAX_BYTES: int = 25 * 1024 * 1024

    # File uploads (User avatars)
    AVATAR_DIR: str = "/app/uploads/avatars"
    AVATAR_MAX_BYTES: int = 5 * 1024 * 1024

    # File uploads (Leave attachments — medical certs, etc.)
    LEAVE_ATTACHMENTS_DIR: str = "/app/uploads/leave-attachments"
    LEAVE_ATTACHMENT_MAX_BYTES: int = 10 * 1024 * 1024

    # File uploads (Project documents — workorder, contracts, etc.)
    PROJECT_DOCUMENTS_DIR: str = "/app/uploads/project-documents"
    PROJECT_DOCUMENT_MAX_BYTES: int = 25 * 1024 * 1024

    SQLALCHEMY_DATABASE_URI: str | None = None

    @field_validator("SQLALCHEMY_DATABASE_URI", mode="before")
    @classmethod
    def assemble_db_connection(cls, v: str | None, info) -> str:
        if isinstance(v, str):
            return v
        user = info.data.get("MARIADB_USER")
        password = info.data.get("MARIADB_PASSWORD")
        server = info.data.get("MARIADB_SERVER")
        port = info.data.get("MARIADB_PORT")
        db = info.data.get("MARIADB_DB")
        return f"mysql+aiomysql://{user}:{password}@{server}:{port}/{db}"

    model_config = SettingsConfigDict(case_sensitive=True, env_file=".env")


settings = Settings()
