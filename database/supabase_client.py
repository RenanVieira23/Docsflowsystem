from supabase import create_client, Client
import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")  # service_role key

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("❌ Erro: SUPABASE_URL ou SUPABASE_KEY não foram carregadas do .env")

# Cliente padrão (publishable) — usado em todas as queries normais
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Cliente admin (service_role) — usado apenas para criar/deletar usuários no Auth
# Se a SERVICE_KEY não estiver configurada, supabase_admin será None
# e as funções de admin vão retornar erro orientativo.
if SUPABASE_SERVICE_KEY:
    supabase_admin: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
else:
    supabase_admin = None
    print("⚠️  SUPABASE_SERVICE_KEY não configurada — gestão de usuários desabilitada.")

print("✅ Conectado ao Supabase com sucesso!")