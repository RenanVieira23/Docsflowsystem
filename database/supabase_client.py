import os
import threading
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL ou SUPABASE_KEY não configuradas")


# ==========================================================
# CLIENT ISOLADO POR SESSÃO — versão determinística (thread-local)
# ==========================================================
# Histórico do problema:
#   v1 (client global único): o token JWT de um usuário sobrescrevia
#   o de outro em tempo real -> dados/rotas trocando entre sessões.
#
#   v2 (contextvars): dependia do Flet reaproveitar a mesma "task"
#   assíncrona para todos os eventos da sessão. Isso não é garantido
#   -> depois do login, as consultas caíam num client sem token
#   aplicado -> RLS bloqueava tudo -> "nenhum dado carregado".
#
# v3 (esta versão): cada usuário tem seu PRÓPRIO objeto Client,
# criado uma vez no login e guardado em page.local_store. Esse
# client nunca é compartilhado por referência ambígua — ele é
# passado EXPLICITAMENTE a cada operação de banco através da
# função run_db() (ver pages/*.py). Dentro da mesma chamada,
# um threading.local() garante que `supabase.table(...)` (usado
# em database/models.py) resolva para o client correto, sem
# depender de nenhum mecanismo implícito do event loop.
# ==========================================================

_thread_local = threading.local()


def new_session_client() -> Client:
    """Cria um Client novo e isolado. Chamar uma vez por sessão,
    logo no início de main(page), e guardar em page.local_store."""
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def run_with_client(client: Client, func, *args, **kwargs):
    """
    Executa func(*args, **kwargs) garantindo que, dentro desta
    thread e apenas durante esta chamada, `supabase` (o proxy usado
    em database/models.py) resolva para `client`.

    NÃO chame diretamente — use run_db() a partir do código das páginas.
    """
    anterior = getattr(_thread_local, "client", None)
    _thread_local.client = client
    try:
        return func(*args, **kwargs)
    finally:
        _thread_local.client = anterior


class _SupabaseProxy:
    """
    Objeto com a mesma interface de um Client do supabase. Toda vez
    que algo em database/models.py faz `supabase.table(...)`,
    `supabase.auth...` etc., essa chamada é resolvida para o client
    que está ativo NESTA thread NESTE momento (definido por
    run_with_client). Fora de uma chamada via run_db(), cai num
    client anônimo novo (sem token) — suficiente para o login,
    mas nunca deve ser usado para dados que dependem de RLS.
    """

    def __getattr__(self, name):
        client = getattr(_thread_local, "client", None)
        if client is None:
            client = create_client(SUPABASE_URL, SUPABASE_KEY)
        return getattr(client, name)


supabase = _SupabaseProxy()

# Client de serviço (admin): usa sempre a chave fixa de service-role,
# nunca recebe token de usuário nenhum — pode continuar global/único,
# não há nenhuma condição de corrida possível aqui.
supabase_admin = (
    create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    if SUPABASE_SERVICE_KEY else None
)


async def run_db(page, func, *args, **kwargs):
    """
    Use esta função em TODAS as páginas no lugar de
    `asyncio.to_thread(func, *args, **kwargs)` sempre que `func`
    for uma função de database/models.py que dependa de estar
    autenticada (RLS). Ela garante que a consulta rode com o
    client autenticado da sessão correta.

    Exemplo:
        # antes:
        clientes = await asyncio.to_thread(get_clientes, tenant_id)
        # depois:
        clientes = await run_db(page, get_clientes, tenant_id)
    """
    import asyncio  # import local para não exigir asyncio em quem só usa supabase/supabase_admin

    client = None
    if hasattr(page, "local_store") and page.local_store:
        client = page.local_store.get("supabase_client")

    if client is None:
        # Rede de segurança: cria um client novo (sem token) para não
        # travar a aplicação, mas isso indica que new_session_client()
        # não foi chamado/guardado corretamente no início da sessão.
        print("⚠️ run_db: sessão sem supabase_client — usando client anônimo.")
        client = new_session_client()

    return await asyncio.to_thread(run_with_client, client, func, *args, **kwargs)