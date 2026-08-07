import os
import threading
import time
import httpx
from supabase import create_client, Client, ClientOptions
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL ou SUPABASE_KEY não configuradas")


# ==========================================================
# FIX CONCORRÊNCIA: "Server disconnected" / ConnectionTerminated
# COMPRESSION_ERROR sob uso simultâneo
# ==========================================================
# O supabase-py (via postgrest-py) cria seu client HTTP interno com
# http2=True fixo. HTTP/2 usa UMA ÚNICA conexão com múltiplos streams
# multiplexados — e como paralelizamos várias operações ao mesmo
# tempo (asyncio.gather rodando em threads separadas via run_db),
# essas threads acabavam usando a MESMA conexão HTTP/2 ao mesmo
# tempo. Se algo nessa concorrência corrompe o estado de compressão
# de cabeçalhos (HPACK) da conexão — coisa que pode acontecer mesmo
# com locking interno do httpx, em cenários de requisição cancelada/
# timeout no meio de um stream — a conexão inteira quebra, e TODAS as
# chamadas seguintes que dependiam dela falham de uma vez (exatamente
# o padrão relatado: várias operações diferentes falhando juntas).
#
# A correção: desativar HTTP/2 (usar HTTP/1.1) e usar um pool de
# várias conexões TCP de verdade. Com HTTP/1.1, concorrência real
# significa conexões SEPARADAS (não streams multiplexados numa só),
# que é o modelo de concorrência que o httpx suporta oficialmente
# para uso a partir de múltiplas threads.
# ==========================================================

def _criar_httpx_client() -> httpx.Client:
    return httpx.Client(
        http2=False,
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        timeout=httpx.Timeout(30.0),
    )


def _client_options() -> ClientOptions:
    """Cada client (de sessão ou admin) recebe seu PRÓPRIO httpx.Client
    configurado sem HTTP/2 — não compartilhamos essa conexão entre
    sessões diferentes, só trocamos a configuração de transporte."""
    return ClientOptions(httpx_client=_criar_httpx_client())


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
    return create_client(SUPABASE_URL, SUPABASE_KEY, options=_client_options())


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
            client = create_client(SUPABASE_URL, SUPABASE_KEY, options=_client_options())
        return getattr(client, name)


supabase = _SupabaseProxy()

# Client de serviço (admin): usa sempre a chave fixa de service-role,
# nunca recebe token de usuário nenhum — pode continuar global/único,
# não há nenhuma condição de corrida de AUTENTICAÇÃO possível aqui.
# (A condição de corrida de CONEXÃO HTTP/2 acima é evitada da mesma
# forma, com o httpx_client customizado sem http2.)
supabase_admin = (
    create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY, options=_client_options())
    if SUPABASE_SERVICE_KEY else None
)


# ==========================================================
# RENOVAÇÃO AUTOMÁTICA DE SESSÃO (refresh token)
# ==========================================================
# O access_token do Supabase Auth expira por padrão em ~1h. Antes
# desta correção, nada renovava esse token — uma sessão longa (ex:
# usuário preenchendo um contrato por mais de 1h) começava a falhar
# silenciosamente com erro de RLS assim que o token vencia, sem
# nenhuma mensagem clara pro usuário.
#
# A cada chamada de run_db(), ANTES de executar a operação, checamos
# se o token está perto de expirar (margem de 2 minutos) e, se
# estiver, renovamos automaticamente usando o refresh_token guardado
# em page.local_store (ver pages/login/view.py — precisa gravar
# session_access_token / session_refresh_token / session_expires_at
# logo após autenticar_usuario()). Isso é transparente: nenhuma tela
# precisa saber que a renovação aconteceu.
#
# Se a renovação falhar de verdade (refresh_token também expirado ou
# revogado — ex: sessão muito antiga, ou logout em outro dispositivo),
# a sessão é encerrada e o usuário é redirecionado ao login com uma
# mensagem clara, em vez de continuar recebendo erros confusos.
# ==========================================================

class SessaoExpiradaError(Exception):
    """Levantada quando a sessão do usuário não pôde ser renovada
    (refresh_token também expirado/inválido) — um novo login é
    necessário."""
    pass


_MARGEM_REFRESH_SEG = 120  # renova o token 2 minutos antes de vencer


def _aplicar_token_no_client(client: Client, token: str):
    """
    Aplica um novo access_token diretamente no client de UMA sessão
    específica (diferente de _apply_access_token em database/models.py,
    que aplica no proxy global `supabase`, resolvido por thread-local).
    Usado logo após renovar o token via refresh_session().
    """
    try:
        client.postgrest.auth(token)
    except Exception as e:
        print(f"⚠️ Erro ao aplicar token renovado no postgrest: {e}")

    try:
        if hasattr(client, "storage") and hasattr(client.storage, "_client"):
            client.storage._client.headers.update({"Authorization": f"Bearer {token}"})
    except Exception as e:
        print(f"⚠️ Erro ao aplicar token renovado no storage: {e}")


async def _garantir_sessao_valida(page, client: Client) -> bool:
    """
    Verifica se o access_token da sessão está perto de expirar e, se
    estiver, renova automaticamente usando o refresh_token guardado
    em page.local_store.

    Retorna True se a sessão está (ou ficou, após renovar) válida.
    Retorna False apenas quando a renovação falhou de verdade — nesse
    caso, quem chamou deve forçar um novo login.
    """
    import asyncio

    if not hasattr(page, "local_store") or page.local_store is None:
        return True  # sem estado de sessão de usuário (ex: fluxo de login)

    expires_at = page.local_store.get("session_expires_at")
    refresh_token = page.local_store.get("session_refresh_token")

    if not expires_at or not refresh_token:
        # Sessão ainda não autenticada, ou logada antes desta versão
        # (sem esses dados gravados) — nada a renovar por aqui.
        return True

    try:
        if time.time() < (float(expires_at) - _MARGEM_REFRESH_SEG):
            return True  # token ainda válido por tempo suficiente
    except (TypeError, ValueError):
        return True  # valor inesperado — não bloqueia a operação por isso

    try:
        resultado = await asyncio.to_thread(client.auth.refresh_session, refresh_token)
    except Exception as ex:
        print(f"⚠️ Falha ao renovar sessão (refresh_token pode estar expirado): {ex}")
        return False

    nova_session = getattr(resultado, "session", None)
    novo_token = getattr(nova_session, "access_token", None) if nova_session else None

    if not novo_token:
        print("⚠️ Renovação de sessão não retornou um access_token válido.")
        return False

    _aplicar_token_no_client(client, novo_token)

    page.local_store["session_access_token"] = novo_token
    page.local_store["session_refresh_token"] = getattr(nova_session, "refresh_token", refresh_token)
    page.local_store["session_expires_at"] = getattr(nova_session, "expires_at", None)

    print("🔄 Sessão renovada automaticamente (token de acesso atualizado).")
    return True


def _finalizar_sessao_expirada(page):
    """
    Limpa os dados de sessão do usuário e força retorno à tela de
    login quando o token não pôde ser renovado. Mantém um client novo
    e limpo em local_store (mesmo padrão usado no logout manual, ver
    app/layout.py -> _logout), para que a próxima tentativa de login
    já tenha um client pronto.
    """
    if not hasattr(page, "local_store") or page.local_store is None:
        return

    tenant_id_anterior = page.local_store.get("tenant_id")
    usuario_nome_anterior = page.local_store.get("usuario_nome")

    try:
        page.local_store.clear()
        page.local_store["supabase_client"] = new_session_client()
    except Exception as e:
        print(f"⚠️ Erro ao limpar sessão expirada: {e}")

    print(
        f"⏳ Sessão expirada — usuário={usuario_nome_anterior or '?'} "
        f"tenant={tenant_id_anterior or '?'} redirecionado ao login."
    )

    try:
        page.go("/login")
    except Exception as e:
        print(f"⚠️ Erro ao redirecionar para /login após expiração: {e}")


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

    RENOVAÇÃO DE SESSÃO: antes de executar a operação, verifica se o
    token de acesso está perto de expirar e renova automaticamente se
    necessário (ver _garantir_sessao_valida acima). Se a renovação
    falhar (sessão expirada de verdade), levanta SessaoExpiradaError
    e já redireciona o usuário para /login.

    LOGGING: qualquer exceção levantada por `func` é automaticamente
    registrada — no console (visível no painel de logs do Render,
    sempre) e na tabela `logs` (nivel="erro", best-effort) — antes de
    ser relançada. Isso dá visibilidade centralizada de falhas
    (timeout, desconexão, erro do Supabase etc.) em QUALQUER tela do
    sistema, sem precisar instrumentar cada try/except manualmente.
    O comportamento de cada tela não muda: a exceção ainda sobe
    normalmente para quem chamou, que continua tratando (snackbar,
    mensagem de erro etc.) como já fazia.
    """
    import asyncio  # import local para não exigir asyncio em quem só usa supabase/supabase_admin

    client = None
    if hasattr(page, "local_store") and page.local_store is not None:
        client = page.local_store.get("supabase_client")

    if client is None:
        # Rede de segurança: cria um client novo (sem token) para não
        # travar a aplicação, mas isso indica que new_session_client()
        # não foi chamado/guardado corretamente no início da sessão
        # (ex: logo após um logout). Guardamos de volta em local_store
        # para as PRÓXIMAS chamadas reaproveitarem o mesmo client —
        # sem isso, cada run_db() criava um client descartável novo,
        # e o token aplicado no login seguinte nunca "grudava" em
        # nenhum lugar persistente.
        print("⚠️ run_db: sessão sem supabase_client — criando um novo.")
        client = new_session_client()
        if hasattr(page, "local_store") and page.local_store is not None:
            page.local_store["supabase_client"] = client

    # Garante que o token ainda é válido — renova automaticamente se
    # estiver perto de expirar. Se não conseguir renovar, encerra a
    # sessão e força novo login em vez de deixar a operação seguir e
    # falhar com um erro confuso de RLS.
    sessao_ok = await _garantir_sessao_valida(page, client)
    if not sessao_ok:
        _finalizar_sessao_expirada(page)
        raise SessaoExpiradaError("Sua sessão expirou. Faça login novamente.")

    nome_func = getattr(func, "__name__", str(func))

    # Cronometragem: ajuda a identificar no log do Render se a lentidão
    # é de uma chamada específica (query lenta, tabela sem índice) ou
    # geral (cold start do servidor, rede). Só imprime se levar > 1.5s
    # para não poluir o console em uso normal.
    inicio = time.perf_counter()
    try:
        resultado = await asyncio.to_thread(run_with_client, client, func, *args, **kwargs)
    except Exception as ex:
        duracao = time.perf_counter() - inicio
        _log_erro_run_db(page, nome_func, ex, duracao)
        raise

    duracao = time.perf_counter() - inicio
    if duracao > 1.5:
        print(f"⏱️  run_db: {nome_func} levou {duracao:.2f}s")

    return resultado


def _log_erro_run_db(page, nome_func: str, ex: Exception, duracao: float):
    """
    Loga uma falha de run_db no console (sempre) e no banco
    (best-effort). Nunca lança exceção própria — um erro ao logar o
    erro original não pode mascarar/substituir o erro original.
    """
    usuario_id = None
    usuario_nome = None
    tenant_id = None
    if hasattr(page, "local_store") and page.local_store is not None:
        usuario_id = page.local_store.get("usuario_id")
        usuario_nome = page.local_store.get("usuario_nome")
        tenant_id = page.local_store.get("tenant_id")

    tipo_erro = type(ex).__name__
    mensagem = str(ex)

    print(
        f"🔴 ERRO_DB [{nome_func}] usuario={usuario_nome or usuario_id or '?'} "
        f"tenant={tenant_id or '?'} apos {duracao:.2f}s — {tipo_erro}: {mensagem}"
    )

    if not tenant_id:
        return  # sem tenant não dá pra gravar (RLS/coluna obrigatória)

    try:
        # Import local para evitar import circular (database.models já
        # importa deste módulo no nível de topo).
        from database.models import registrar_log_erro
        registrar_log_erro(
            tenant_id=tenant_id,
            usuario_id=usuario_id,
            contexto=f"Erro em {nome_func}",
            erro=f"{tipo_erro}: {mensagem} (após {duracao:.2f}s)",
        )
    except Exception as erro_log:
        print(f"❌ Também falhou ao registrar o erro acima no banco: {erro_log}")