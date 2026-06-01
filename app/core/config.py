import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    # App
    APP_NAME: str = "Ar-Learn API"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = os.getenv("APP_ENV", "development")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-change-in-production")

    # Supabase
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")           # service_role
    SUPABASE_ANON_KEY: str = os.getenv("SUPABASE_ANON_KEY", "") # anon public

    # Redis (Upstash)
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")

    # File upload
    MAX_UPLOAD_SIZE_MB: int = 20  # For PDFs, spreadsheets, etc.

    # Cache TTL (in seconds)
    CACHE_TTL_SHORT: int = 300    # 5 minutes
    CACHE_TTL_LONG: int = 3600    # 1 hour

    # AI / Remark generation mode
    AI_MODE: str = "rule-based"   # "rule-based" for Phase 1, later "llm"

    class Config:
        case_sensitive = True

settings = Settings()