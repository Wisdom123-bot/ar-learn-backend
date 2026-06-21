import os
from dotenv import load_dotenv
from supabase import create_client, Client, ClientOptions

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Missing Supabase environment variables. Check your .env file.")

# Initialization
# SCALABILITY NOTE: For high-traffic (10k RPM), ensure SUPABASE_URL 
# in production uses the Transaction Pooler (Port 6543) instead of 
# the direct connection (Port 5432) to prevent "Too many connections" errors.
supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_KEY,
    options=ClientOptions(
        postgrest_client_timeout=45,
        storage_client_timeout=45,
    )
)

def get_supabase() -> Client:
    """Dependency that returns the Supabase client."""
    return supabase