# database/models.py
import os
import re
import json
import requests
from datetime import datetime, timedelta
from functools import lru_cache
from dotenv import load_dotenv

from database.supabase_client import supabase, supabase_admin

load_dotenv()


# ======================================================
# HELPERS
# ======================================================

def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _safe_exec(query, msg="Erro Supabase"):
    try:
        return query.execute()
    except Exception as e:
        print(f"❌ {msg}: {e}")
        return None

def _as_bool(v):
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    if isinstance(v, (int, float)):
        return v == 1
    if isinstance(v, str):
        return v.strip().lower() in ("true", "t", "1", "yes", "y", "sim")
    return False


# ======================================================
# TOKEN (para Edge Functions com Bearer)
# ======================================================

_CURRENT_ACCESS_TOKEN = None

def _set_current_access_token(token):
    global _CURRENT_ACCESS_TOKEN
    _CURRENT_ACCESS_TOKEN = token

def _get_current_access_token():
    return _CURRENT_ACCESS_TOKEN

def _apply_access_token(token: str):
    if not token:
        return

    _set_current_access_token(token)

    # PostgREST
    try:
        supabase.postgrest.auth(token)
    except Exception as e:
        print(f"❌ Erro ao aplicar token no postgrest: {e}")

    # Storage
    try:
        if hasattr(supabase, "storage") and hasattr(supabase.storage, "_client"):
            supabase.storage._client.headers.update({"Authorization": f"Bearer {token}"})
    except Exception as e:
        print(f"⚠️ Aviso: não foi possível aplicar token no storage client: {e}")

    # Functions
    try:
        if hasattr(supabase, "functions"):
            if hasattr(supabase.functions, "_client"):
                supabase.functions._client.headers.update({"Authorization": f"Bearer {token}"})
            elif hasattr(supabase.functions, "headers") and isinstance(supabase.functions.headers, dict):
                supabase.functions.headers["Authorization"] = f"Bearer {token}"
    except Exception as e:
        print(f"⚠️ Aviso: não foi possível aplicar token no functions client: {e}")


def _merge_admin_flags(perfil: dict, auth_user) -> dict:
    if perfil is None:
        perfil = {}

    db_is_admin = perfil.get("is_admin")
    db_is_global_admin = perfil.get("is_global_admin")

    meta_user = getattr(auth_user, "user_metadata", {}) or {}
    meta_app = getattr(auth_user, "app_metadata", {}) or {}

    meta_is_admin = meta_user.get("is_admin", meta_app.get("is_admin"))
    meta_is_global_admin = meta_user.get("is_global_admin", meta_app.get("is_global_admin"))

    perfil["is_admin"] = _as_bool(db_is_admin) if db_is_admin is not None else _as_bool(meta_is_admin)
    perfil["is_global_admin"] = _as_bool(db_is_global_admin) if db_is_global_admin is not None else _as_bool(meta_is_global_admin)

    return perfil


# ======================================================
# 📊 CACHE (MULTI-TENANT)
# ======================================================

@lru_cache(maxsize=32)
def _cache_clientes(tenant_id: str):
    try:
        resp = _safe_exec(
            supabase.table("clientes")
            .select("*")
            .eq("tenant_id", tenant_id),
            "Erro cache clientes"
        )
        return resp.data if resp else []
    except Exception as e:
        print(f"❌ erro cache clientes: {e}")
        return []


@lru_cache(maxsize=32)
def _cache_contratos(tenant_id: str):
    try:
        resp = _safe_exec(
            supabase.table("contratos")
            .select("*")
            .eq("tenant_id", tenant_id),
            "Erro cache contratos"
        )
        return resp.data if resp else []
    except Exception as e:
        print(f"❌ erro cache contratos: {e}")
        return []


def _clear_cache():
    try:
        _cache_clientes.cache_clear()
        _cache_contratos.cache_clear()
    except Exception as e:
        print(f"❌ erro ao limpar cache: {e}")


# ======================================================
# AUTH + PERFIL
# ======================================================

def autenticar_usuario(email: str, senha: str):
    try:
        res = supabase.auth.sign_in_with_password({
            "email": (email or "").strip(),
            "password": (senha or "").strip(),
        })

        if not res or not getattr(res, "session", None) or not getattr(res, "user", None):
            return None

        auth_uid = str(res.user.id)
        token = res.session.access_token
        _apply_access_token(token)

        prof = (
            supabase.table("usuarios")
            .select("*")
            .eq("auth_uid", auth_uid)
            .maybe_single()
            .execute()
        )

        perfil = prof.data if prof else None

        if not perfil:
            return {"_error": "PERFIL_NAO_ENCONTRADO"}

        tenant_id = perfil.get("tenant_id")
        tenant_nome = "Tenant"

        if tenant_id:
            tenant = get_tenant_por_id(tenant_id)
            if tenant:
                tenant_nome = tenant.get("nome")

        perfil = _merge_admin_flags(perfil, res.user)

        perfil["_session"] = {
            "access_token": token,
            "refresh_token": res.session.refresh_token,
            "expires_at": res.session.expires_at,
            "auth_uid": auth_uid,
        }

        perfil["tenant_nome"] = tenant_nome

        return perfil

    except Exception as e:
        print(f"❌ Erro ao autenticar/buscar perfil: {e}")
        return None


def get_perfil_por_auth_uid(auth_uid: str):
    try:
        resp = supabase.table("usuarios").select("*").eq("auth_uid", str(auth_uid)).maybe_single().execute()
        return resp.data if resp else None
    except Exception as e:
        print(f"❌ Erro ao buscar perfil por auth_uid: {e}")
        return None


def get_tenant_por_id(tenant_id):
    try:
        resp = (
            supabase
            .table("tenants")
            .select("id, nome")
            .eq("id", tenant_id)
            .maybe_single()
            .execute()
        )
        return resp.data if resp else None
    except Exception as e:
        print(f"❌ Erro ao buscar tenant: {e}")
        return None


# ======================================================
# 👥 CLIENTES
# ======================================================

def get_clientes(tenant_id: str, force=False):
    try:
        if force:
            _clear_cache()

        return list(_cache_clientes(tenant_id))

    except Exception as e:
        print(f"❌ erro clientes: {e}")
        return []


def add_cliente(cliente: dict):
    try:
        if "tenant_id" not in cliente:
            raise Exception("tenant_id obrigatório")
        data = supabase.table("clientes").insert(cliente).execute()
        _clear_cache()
        return data.data[0] if data.data else None
    except Exception as e:
        print(f"❌ erro add cliente: {e}")
        return None


def delete_cliente(cliente_id: int):
    try:
        supabase.table("clientes").delete().eq("id", cliente_id).execute()
        _clear_cache()
    except Exception as e:
        print(f"❌ erro delete cliente: {e}")


def update_cliente(cliente_id: int, dados: dict):
    try:
        resp = (
            supabase.table("clientes")
            .update(dados)
            .eq("id", cliente_id)
            .execute()
        )
        _clear_cache()
        return resp.data[0] if resp.data else None
    except Exception as e:
        print(f"❌ erro update cliente: {e}")
        return None


# ======================================================
# 📄 CONTRATOS
# ======================================================

def get_contratos(tenant_id: str):
    try:
        return list(_cache_contratos(tenant_id))
    except Exception as e:
        print(f"❌ Erro ao buscar contratos: {e}")
        return []


def get_contratos_por_cliente(cliente_id: int, tenant_id: str):
    try:
        data = (
            supabase.table("contratos")
            .select("*")
            .eq("cliente_id", cliente_id)
            .eq("tenant_id", tenant_id)
            .execute()
        )
        return data.data if data.data else []
    except Exception as e:
        print(f"❌ Erro ao buscar contratos do cliente {cliente_id}: {e}")
        return []


def add_contrato(contrato: dict):
    try:
        if "tenant_id" not in contrato:
            raise Exception("tenant_id obrigatório no contrato")
        resp = supabase.table("contratos").insert(contrato).execute()
        _clear_cache()
        return resp.data[0] if resp.data else None
    except Exception as e:
        print(f"❌ Erro ao adicionar contrato: {e}")
        return None


def delete_contrato(contrato_id: int):
    try:
        supabase.table("contratos").delete().eq("id", contrato_id).execute()
        _clear_cache()
    except Exception as e:
        print(f"❌ Erro ao deletar contrato: {e}")


def update_contrato(contrato_id: int, dados: dict):
    try:
        resp = (
            supabase.table("contratos")
            .update(dados)
            .eq("id", contrato_id)
            .execute()
        )
        _clear_cache()
        return resp.data[0] if resp.data else None
    except Exception as e:
        print(f"❌ Erro ao atualizar contrato: {e}")
        return None


# ======================================================
# PRAZOS
# ======================================================

def add_prazo(contrato_id, meses, observacao, data_criacao, data_vencimento, tenant_id, tipo=None):
    """
    data_criacao = "Data Início" do prazo na tela (pode ser diferente da
    data de assinatura do contrato). data_vencimento = calculada
    automaticamente na tela como data_criacao + meses.
    """
    try:
        novo_prazo = {
            "contrato_id": contrato_id,
            "meses": meses or 0,
            "observacao": observacao or "",
            "data_criacao": data_criacao or datetime.now().strftime("%Y-%m-%d"),
            "data_vencimento": data_vencimento,
            "tenant_id": tenant_id,  # ← obrigatório para RLS
            "tipo": tipo,
        }
        resp = supabase.table("prazos").insert(novo_prazo).execute()
        return resp.data[0] if resp.data else novo_prazo
    except Exception as e:
        print(f"❌ Erro ao adicionar prazo: {e}")
        return None


def get_prazos_por_contrato(contrato_id):
    try:
        data = supabase.table("prazos").select("*").eq("contrato_id", contrato_id).execute()
        return data.data if data.data else []
    except Exception as e:
        print(f"❌ Erro ao buscar prazos: {e}")
        return []


def update_prazo(prazo_id: int, dados: dict):
    try:
        if not prazo_id:
            raise Exception("prazo_id inválido")
        resp = supabase.table("prazos").update(dados).eq("id", prazo_id).execute()
        return resp.data[0] if resp.data else None
    except Exception as e:
        print("❌ Erro ao atualizar prazo:", e)
        return None


# ======================================================
# NOTIFICAÇÕES
# FIX RLS: tenant_id agora obrigatório no insert
# ======================================================

def add_notificacao(prazo_id, tenant_id: str, dias_antes=None, data_enviada=None):
    """
    tenant_id é obrigatório para passar na política RLS de INSERT.
    """
    try:
        if not tenant_id:
            raise Exception("tenant_id obrigatório em add_notificacao")
        nova = {
            "prazo_id": prazo_id,
            "dias_antes": dias_antes or 0,
            "data_enviada": data_enviada or datetime.now().strftime("%Y-%m-%d"),
            "tenant_id": tenant_id,  # ← obrigatório para RLS
        }
        resp = supabase.table("notificacoes_enviadas").insert(nova).execute()
        return resp.data[0] if resp.data else nova
    except Exception as e:
        print(f"❌ Erro ao adicionar notificação: {e}")
        return None


def get_notificacoes_por_prazo(prazo_id):
    try:
        resp = supabase.table("notificacoes_enviadas").select("*").eq("prazo_id", prazo_id).execute()
        return resp.data if resp.data else []
    except Exception as e:
        print(f"❌ Erro ao buscar notificações: {e}")
        return []


# ======================================================
# TIPOS DE NOTIFICAÇÃO
# (tabela sem tenant_id — política libera para autenticados)
# ======================================================

def get_tipos_notificacao():
    try:
        resp = supabase.table("tipos_notificacao").select("*").order("nome").execute()
        return resp.data if resp.data else []
    except Exception as e:
        print(f"❌ Erro ao buscar tipos de notificação: {e}")
        return []


def add_tipo_notificacao(nome: str):
    try:
        payload = {"nome": (nome or "").strip(), "ativo": True}
        resp = supabase.table("tipos_notificacao").insert(payload).execute()
        return resp.data[0] if resp.data else payload
    except Exception as e:
        print(f"❌ Erro ao adicionar tipo de notificação: {e}")
        return None


def update_tipo_notificacao(tipo_id: int, dados: dict):
    try:
        resp = supabase.table("tipos_notificacao").update(dados).eq("id", tipo_id).execute()
        return resp.data[0] if resp.data else None
    except Exception as e:
        print(f"❌ Erro ao atualizar tipo de notificação: {e}")
        return None


def delete_tipo_notificacao(tipo_id: int):
    try:
        supabase.table("tipos_notificacao").delete().eq("id", tipo_id).execute()
        return True
    except Exception as e:
        print(f"❌ Erro ao deletar tipo de notificação: {e}")
        return False


# ======================================================
# LOGS
# FIX RLS: tenant_id agora obrigatório no insert
# ======================================================

def registrar_log(usuario_id, acao, detalhes=None, tenant_id=None):
    """
    tenant_id é obrigatório para passar na política RLS de INSERT.
    Se não for fornecido, o log é silenciosamente ignorado para não
    quebrar o fluxo principal da aplicação.
    """
    try:
        if not tenant_id:
            print(f"⚠️ registrar_log: tenant_id não fornecido, log ignorado (acao={acao})")
            return
        novo = {
            "usuario_id": usuario_id,
            "acao": acao,
            "detalhes": detalhes,
            "data_hora": _now(),
            "tenant_id": tenant_id,  # ← obrigatório para RLS
        }
        supabase.table("logs").insert(novo).execute()
    except Exception as e:
        print(f"❌ Erro ao registrar log: {e}")


# ======================================================
# ANEXOS
# FIX RLS: tenant_id agora obrigatório no insert
# ======================================================

def add_anexo(contrato_id, nome_arquivo, tenant_id: str, arquivo_url=None, arquivo_path=None):
    """
    tenant_id é obrigatório para passar na política RLS de INSERT.
    """
    try:
        if not tenant_id:
            raise Exception("tenant_id obrigatório em add_anexo")
        novo = {
            "contrato_id": contrato_id,
            "nome_arquivo": nome_arquivo,
            "arquivo_url": arquivo_url,
            "arquivo_path": arquivo_path,
            "tenant_id": tenant_id,  # ← obrigatório para RLS
        }
        resp = supabase.table("anexos").insert(novo).execute()
        return resp.data[0] if resp.data else novo
    except Exception as e:
        print(f"❌ Erro ao adicionar anexo: {e}")
        return None


def get_anexos_por_contrato(contrato_id):
    resp = (
        supabase
        .table("anexos")
        .select("*")
        .eq("contrato_id", contrato_id)
        .execute()
    )
    return resp.data or []


# ======================================================
# DASHBOARD / RELATÓRIOS
# Com RLS ativo, as queries abaixo auto-filtram pelo tenant
# do usuário logado via JWT — não precisam de tenant_id explícito.
# ======================================================

def get_total_prazos():
    try:
        resp = supabase.table("prazos").select("id", count="exact").execute()
        return resp.count or 0
    except Exception as e:
        print(f"❌ Erro ao contar prazos: {e}")
        return 0


def get_total_alertas_enviados():
    try:
        resp = supabase.table("notificacoes_enviadas").select("id", count="exact").execute()
        return resp.count or 0
    except Exception as e:
        print(f"❌ Erro ao contar notificações: {e}")
        return 0


def get_relatorio_notificacoes_paginado(status="todos", limit=50, offset=0):
    try:
        query = supabase.table("prazos").select("""
            id, observacao, data_criacao, data_vencimento,
            contratos (nome, data_inicial, clientes (nome)),
            notificacoes_enviadas (dias_antes, data_enviada)
        """).range(offset, offset + limit - 1)
        data = query.execute().data or []
        return _formatar_relatorio(data, status)
    except Exception as e:
        print(f"❌ Erro relatório paginado: {e}")
        return []


def get_relatorio_notificacoes_export(status="todos"):
    try:
        query = supabase.table("prazos").select("""
            id, observacao, data_criacao, data_vencimento,
            contratos (nome, data_inicial, clientes (nome)),
            notificacoes_enviadas (dias_antes, data_enviada)
        """)
        data = query.execute().data or []
        return _formatar_relatorio(data, status)
    except Exception as e:
        print(f"❌ Erro relatório export: {e}")
        return []


def get_total_notificacoes(status="todos"):
    try:
        query = supabase.table("prazos").select("id", count="exact")
        return query.execute().count or 0
    except Exception as e:
        print(f"❌ Erro total relatório: {e}")
        return 0


def _formatar_relatorio(dados, status):
    rel = []
    for p in dados:
        notif = p.get("notificacoes_enviadas") or []
        enviado = len(notif) > 0
        if status == "enviados" and not enviado:
            continue
        if status == "pendentes" and enviado:
            continue
        contrato = p.get("contratos") or {}
        cliente = (contrato.get("clientes") or {}).get("nome", "-")
        rel.append({
            "cliente": cliente,
            "contrato": contrato.get("nome", "-"),
            "observacao": p.get("observacao") or "-",
            "inicio": contrato.get("data_inicial"),
            "vencimento": p.get("data_vencimento"),
            "dias_antes": (notif[0].get("dias_antes") if enviado else "-"),
            "status": "Enviado" if enviado else "Pendente",
        })
    return rel


# ======================================================
# ALERTAS
# Com RLS, auto-filtra pelo tenant do JWT.
# ======================================================

def get_alertas_por_periodo(dias=7):
    try:
        hoje = datetime.now().date()
        limite = hoje + timedelta(days=dias)
        prazos = supabase.table("prazos").select("""
            id, observacao, data_vencimento,
            contratos (nome, clientes (nome))
        """).gte("data_vencimento", hoje.isoformat()).lte("data_vencimento", limite.isoformat()).execute().data or []
        enviados = supabase.table("notificacoes_enviadas").select("prazo_id").execute()
        enviados_ids = {n["prazo_id"] for n in (enviados.data or [])}
        dados = []
        for p in prazos:
            venc = datetime.strptime(p["data_vencimento"], "%Y-%m-%d").date()
            dias_rest = (venc - hoje).days
            status = "Enviado" if p["id"] in enviados_ids else "Pendente"
            dados.append({
                "cliente": p["contratos"]["clientes"]["nome"],
                "contrato": p["contratos"]["nome"],
                "observacao": p["observacao"],
                "vencimento": p["data_vencimento"],
                "dias": dias_rest,
                "status": status
            })
        return dados
    except Exception as e:
        print(f"❌ Erro painel alertas: {e}")
        return []


# ======================================================
# ADMIN (Edge Function)
# ======================================================

BASE = f"{os.getenv('SUPABASE_URL')}/functions/v1/admin-users"
HEADERS = {
    "Content-Type": "application/json",
    "apikey": os.getenv("SUPABASE_SERVICE_ROLE_KEY")
}


def _call(payload):
    try:
        r = requests.post(BASE, json=payload, headers=HEADERS, timeout=20)
        data = r.json()
        if r.status_code != 200 or not data.get("ok"):
            return False, data.get("message")
        return True, data.get("data")
    except Exception as e:
        return False, str(e)


def listar_usuarios_admin():
    return _call({"action": "list"})


# ======================================================
# 👤 PARTES
# get_partes(tenant_id) filtra explicitamente por tenant_id
# (além do RLS via JWT) — mesmo padrão de get_clientes(),
# get_contratos() etc. tenant_id é opcional só por retrocompat;
# sempre que possível, chame passando o tenant_id da sessão.
# add_parte: o dict deve conter tenant_id — veja partes/form.py
# ======================================================

def get_partes(tenant_id: str = None):
    try:
        query = supabase.table("partes").select("*").order("nome")
        if tenant_id:
            query = query.eq("tenant_id", tenant_id)
        resp = _safe_exec(query, "Erro partes")
        return resp.data if resp else []
    except Exception as e:
        print(f"❌ Erro ao buscar partes: {e}")
        return []


def add_parte(parte: dict):
    """
    parte deve conter tenant_id para passar na política RLS de INSERT.
    Ex: add_parte({"nome": ..., "tipo": ..., "documento": ..., "tenant_id": tid})
    """
    try:
        if "tenant_id" not in parte:
            raise Exception("tenant_id obrigatório em add_parte")
        resp = supabase.table("partes").insert(parte).execute()
        return resp.data[0] if resp.data else None
    except Exception as e:
        print(f"❌ Erro ao adicionar parte: {e}")
        return None


def update_parte(parte_id: int, dados: dict):
    try:
        resp = (
            supabase.table("partes")
            .update(dados)
            .eq("id", parte_id)
            .execute()
        )
        return resp.data[0] if resp.data else None
    except Exception as e:
        print(f"❌ Erro ao atualizar parte: {e}")
        return None


# ======================================================
# 🏷️ TIPOS DE PARTES
# (tabela tipos_partes — sem tenant_id no schema)
# ======================================================

def get_tipos_partes():
    try:
        tenant_id = get_tenant_id()

        resp = _safe_exec(
            supabase.table("tipos_partes")
            .select("*")
            .eq("tenant_id", tenant_id)
            .order("nome"),
            "Erro tipos_partes"
        )

        return resp.data if resp else []

    except Exception as e:
        print(f"❌ Erro ao buscar tipos de partes: {e}")
        return []


def add_tipo_parte(nome: str):
    try:
        tenant_id = get_tenant_id()

        resp = supabase.table("tipos_partes").insert({
            "nome": nome.strip(),
            "tenant_id": tenant_id,
        }).execute()

        return resp.data[0] if resp.data else None

    except Exception as e:
        print(f"❌ Erro ao adicionar tipo de parte: {e}")
        return None


def update_tipo_parte(tipo_id: int, dados: dict):
    try:
        tenant_id = get_tenant_id()

        resp = (
            supabase.table("tipos_partes")
            .update(dados)
            .eq("id", tipo_id)
            .eq("tenant_id", tenant_id)
            .execute()
        )

        return resp.data[0] if resp.data else None

    except Exception as e:
        print(f"❌ Erro ao atualizar tipo de parte: {e}")
        return None

def delete_tipo_parte(tipo_id: int):
    try:
        tenant_id = get_tenant_id()

        supabase.table("tipos_partes") \
            .delete() \
            .eq("id", tipo_id) \
            .eq("tenant_id", tenant_id) \
            .execute()

        return True

    except Exception as e:
        print(f"❌ Erro ao deletar tipo de parte: {e}")
        return False
# ======================================================
# 🔗 CONTRATO_PARTES
# FIX RLS: tenant_id agora obrigatório no insert
# ======================================================

def get_contrato_partes(contrato_id: int):
    try:
        resp = (
            supabase.table("contrato_partes")
            .select("*")
            .eq("contrato_id", contrato_id)
            .execute()
        )
        return resp.data if resp.data else []
    except Exception as e:
        print(f"❌ Erro ao buscar partes do contrato: {e}")
        return []


def add_contrato_parte(contrato_id: int, parte_id: int, tipo_vinculo: str, tenant_id: str):
    """
    tenant_id é obrigatório para passar na política RLS de INSERT.

    Usa upsert (não insert puro): se a mesma combinação
    contrato_id + parte_id + tipo_vinculo já existir, apenas retorna
    a linha existente em vez de dar erro de duplicidade. Isso torna
    seguro tentar de novo automaticamente se a conexão cair no meio
    do envio (ver _run_db_com_retry em pages/contratos/form.py) —
    sem isso, uma nova tentativa depois de uma falha de rede poderia
    criar linha duplicada ou falhar por violação de unicidade.

    Requer a constraint única (contrato_id, parte_id, tipo_vinculo)
    na tabela — ver instruções de SQL fornecidas.
    """
    try:
        if not tenant_id:
            raise Exception("tenant_id obrigatório em add_contrato_parte")
        payload = {
            "contrato_id": contrato_id,
            "parte_id": parte_id,
            "tipo_vinculo": tipo_vinculo,
            "tenant_id": tenant_id,  # ← obrigatório para RLS
        }
        resp = (
            supabase.table("contrato_partes")
            .upsert(payload, on_conflict="contrato_id,parte_id,tipo_vinculo")
            .execute()
        )
        return resp.data[0] if resp.data else None
    except Exception as e:
        print(f"❌ Erro ao adicionar parte ao contrato: {e}")
        return None


def delete_contrato_parte(cp_id: int):
    try:
        supabase.table("contrato_partes").delete().eq("id", cp_id).execute()
        return True
    except Exception as e:
        print(f"❌ Erro ao remover parte do contrato: {e}")
        return False


# ======================================================
# 👥 GESTÃO DE USUÁRIOS (sempre via supabase_admin)
# ======================================================

def get_usuarios_do_tenant(tenant_id: str) -> list:
    """Lista usuários do tenant via service role (bypass RLS intencional)."""
    try:
        client = supabase_admin or supabase
        resp = (
            client.table("usuarios")
            .select("*")
            .eq("tenant_id", tenant_id)
            .order("usuario")
            .execute()
        )
        return resp.data or []
    except Exception as e:
        print(f"❌ Erro ao listar usuários: {e}")
        return []


def get_usuarios() -> list:
    """Lista todos os usuários sem filtro de tenant (admin global)."""
    try:
        client = supabase_admin or supabase
        resp = (
            client.table("usuarios")
            .select("*")
            .order("usuario")
            .execute()
        )
        return resp.data or []
    except Exception as e:
        print(f"❌ Erro ao listar usuários: {e}")
        return []


def criar_usuario_admin(
    email: str,
    senha: str,
    nome_usuario: str,
    tenant_id: str,
    role: str = "user",
    is_admin: bool = False,
) -> dict:

    if not supabase_admin:
        return {"_error": "SUPABASE_SERVICE_KEY não configurada"}

    email = email.strip().lower()
    nome_usuario = nome_usuario.strip()
    auth_uid = None

    try:
        res = supabase_admin.auth.admin.create_user({
            "email": email,
            "password": senha,
            "email_confirm": True,
            "user_metadata": {"display_name": nome_usuario},
        })

        auth_uid = str(res.user.id)

        perfil = {
            "usuario": nome_usuario,
            "email": email,
            "auth_uid": auth_uid,
            "tenant_id": tenant_id,
            "role": role,
            "is_admin": is_admin,
        }

        resp = (
            supabase_admin
            .table("usuarios")
            .insert(perfil)
            .execute()
        )

        return resp.data[0] if resp.data else perfil

    except Exception as e:
        try:
            if auth_uid:
                supabase_admin.auth.admin.delete_user(auth_uid)
        except Exception:
            pass
        return {"_error": str(e)}


def update_usuario_admin(usuario_id: int, dados: dict) -> dict:
    senha = dados.pop("senha", None)

    try:
        resp = (
            supabase_admin
            .table("usuarios")
            .update(dados)
            .eq("id", usuario_id)
            .execute()
        )
        perfil = resp.data[0] if resp.data else {}
    except Exception as e:
        return {"_error": str(e)}

    if senha and perfil.get("auth_uid"):
        try:
            supabase_admin.auth.admin.update_user_by_id(
                perfil["auth_uid"],
                {"password": senha},
            )
        except Exception as e:
            print(f"⚠️ Erro ao atualizar senha: {e}")

    return perfil


def delete_usuario_admin(usuario_id: int) -> bool:
    try:
        resp = (
            supabase_admin
            .table("usuarios")
            .select("auth_uid")
            .eq("id", usuario_id)
            .single()
            .execute()
        )

        auth_uid = resp.data.get("auth_uid") if resp.data else None

        supabase_admin.table("usuarios") \
            .delete() \
            .eq("id", usuario_id) \
            .execute()

        if auth_uid:
            supabase_admin.auth.admin.delete_user(auth_uid)

        return True

    except Exception as e:
        print(f"❌ Erro ao deletar usuário: {e}")
        return False


# ======================================================
# 🔗 VÍNCULOS (tipos de partes)
# ======================================================

def get_vinculos(tenant_id: str = None) -> list:
    try:
        q = supabase.table("vinculos").select("*")
        if tenant_id:
            q = q.eq("tenant_id", tenant_id)
        resp = q.order("tipo").execute()
        return resp.data if resp.data else []
    except Exception as e:
        print(f"❌ Erro ao buscar vínculos: {e}")
        return []


def add_vinculo(tipo: str, tenant_id: str):
    try:
        resp = supabase.table("vinculos").insert({
            "tipo": tipo.strip(),
            "tenant_id": tenant_id
        }).execute()
        return resp.data[0] if resp.data else {}
    except Exception as e:
        print(f"❌ Erro ao adicionar vínculo: {e}")
        return {"_error": str(e)}


def delete_vinculo(vinculo_id: int) -> bool:
    try:
        supabase.table("vinculos").delete().eq("id", vinculo_id).execute()
        return True
    except Exception as e:
        print(f"❌ Erro ao deletar vínculo: {e}")
        return False


def update_vinculo(vinculo_id: int, dados: dict) -> dict:
    try:
        tipo = (dados.get("tipo") or "").strip()
        if not tipo:
            return {"_error": "Tipo inválido."}
        resp = (
            supabase
            .table("vinculos")
            .update({"tipo": tipo})
            .eq("id", vinculo_id)
            .execute()
        )
        return resp.data[0] if resp.data else {}
    except Exception as e:
        print(f"❌ Erro ao atualizar vínculo: {e}")
        return {"_error": str(e)}


# ======================================================
# 📄 TIPOS DE CONTRATOS
# Função única consolidada (havia duplicata no código original).
# Com RLS ativo, o SELECT auto-filtra pelo tenant do JWT.
# ======================================================

def get_tipos_contratos(tenant_id: str = None):
    try:
        q = supabase.table("tipos_contratos").select("*").order("nome")
        # filtro explícito opcional — com RLS já está filtrado pelo JWT
        if tenant_id:
            q = q.eq("tenant_id", tenant_id)
        resp = _safe_exec(q, "Erro tipos_contratos")
        return resp.data if resp else []
    except Exception as e:
        print(f"❌ Erro ao buscar tipos de contratos: {e}")
        return []


def add_tipo_contrato(nome: str, tenant_id: str):
    try:
        resp = supabase.table("tipos_contratos").insert({
            "nome": nome.strip(),
            "tenant_id": tenant_id
        }).execute()
        return resp.data[0] if resp.data else None
    except Exception as e:
        print(f"❌ Erro ao adicionar tipo de contrato: {e}")
        return None


def update_tipo_contrato(tipo_id: int, dados: dict):
    try:
        resp = (
            supabase.table("tipos_contratos")
            .update(dados)
            .eq("id", tipo_id)
            .execute()
        )
        return resp.data[0] if resp.data else None
    except Exception as e:
        print(f"❌ Erro ao atualizar tipo de contrato: {e}")
        return None


def delete_tipo_contrato(tipo_id: int):
    try:
        supabase.table("tipos_contratos").delete().eq("id", tipo_id).execute()
        return True
    except Exception as e:
        print(f"❌ Erro ao deletar tipo de contrato: {e}")
        return False


# ======================================================
# ⏰ TIPOS DE PRAZOS
# Função única consolidada (havia duplicata no código original).
# ======================================================

def get_tipos_prazos(tenant_id: str = None):
    try:
        q = supabase.table("tipos_prazos").select("*").order("nome")
        if tenant_id:
            q = q.eq("tenant_id", tenant_id)
        resp = _safe_exec(q, "Erro tipos_prazos")
        return resp.data if resp else []
    except Exception as e:
        print(f"❌ Erro ao buscar tipos de prazos: {e}")
        return []


# Alias mantido para compatibilidade com chamadas antigas
def get_tipos_prazos_db(tenant_id: str = None) -> list:
    return get_tipos_prazos(tenant_id)


def add_tipo_prazo(nome: str, tenant_id: str):
    try:
        resp = supabase.table("tipos_prazos").insert({
            "nome": nome.strip(),
            "tenant_id": tenant_id
        }).execute()
        return resp.data[0] if resp.data else None
    except Exception as e:
        print(f"❌ Erro ao adicionar tipo de prazo: {e}")
        return None


# Alias mantido para compatibilidade
def add_tipo_prazo_db(nome: str, tenant_id: str) -> dict:
    result = add_tipo_prazo(nome, tenant_id)
    return result or {}


def update_tipo_prazo(tipo_id: int, dados: dict):
    try:
        resp = (
            supabase.table("tipos_prazos")
            .update(dados)
            .eq("id", tipo_id)
            .execute()
        )
        return resp.data[0] if resp.data else None
    except Exception as e:
        print(f"❌ Erro ao atualizar tipo de prazo: {e}")
        return None


def delete_tipo_prazo(tipo_id: int):
    try:
        supabase.table("tipos_prazos").delete().eq("id", tipo_id).execute()
        return True
    except Exception as e:
        print(f"❌ Erro ao deletar tipo de prazo: {e}")
        return False


# Alias mantido para compatibilidade
def delete_tipo_prazo_db(tipo_id: int) -> bool:
    return delete_tipo_prazo(tipo_id)


# ======================================================
# STORAGE PRIVADO "Heringer"
# ======================================================
STORAGE_BUCKET = "Heringer"


def list_anexos_storage(contrato_id: int):
    pasta = f"contratos/{contrato_id}/anexos"
    try:
        files = supabase.storage.from_(STORAGE_BUCKET).list(pasta)
        anexos = []
        for f in files:
            nome = f.get("name")
            if not nome or nome.startswith("."):
                continue
            anexos.append({
                "nome_arquivo": nome,
                "arquivo_path": f"{pasta}/{nome}",
            })
        return anexos
    except Exception as e:
        print("❌ erro list storage:", e)
        return []


EXTENSOES_ANEXO_PERMITIDAS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".jpg", ".jpeg", ".png", ".txt",
}


def _sanitizar_nome_arquivo(nome: str) -> str:
    """
    Remove caracteres perigosos do nome do arquivo antes de montar o
    caminho no Storage — evita que um nome como '../../outro/arquivo'
    tente escrever fora da pasta do contrato.
    """
    nome = os.path.basename(nome or "arquivo")
    nome = re.sub(r"[^A-Za-z0-9._-]", "_", nome)
    return nome or "arquivo"


def upload_anexo_storage(contrato_id, nome_arquivo, file_bytes):
    nome_seguro = _sanitizar_nome_arquivo(nome_arquivo)

    ext = os.path.splitext(nome_seguro)[1].lower()
    if ext not in EXTENSOES_ANEXO_PERMITIDAS:
        raise ValueError(f"Tipo de arquivo não permitido: {ext or 'sem extensão'}")

    caminho = f"contratos/{contrato_id}/anexos/{nome_seguro}"
    client = supabase_admin or supabase
    client.storage.from_(STORAGE_BUCKET).upload(
        path=caminho,
        file=file_bytes,
        file_options={"upsert": "true"},
    )
    return {
        "nome_arquivo": nome_seguro,
        "arquivo_path": caminho,
    }


def delete_anexo_storage(arquivo_path: str) -> bool:
    if not arquivo_path:
        return False
    try:
        supabase.storage.from_(STORAGE_BUCKET).remove([arquivo_path])
        return True
    except Exception as e:
        print(f"❌ erro delete_anexo_storage: {e}")
        return False


def get_anexo_signed_url(arquivo_path: str, expires_in: int = 3600) -> str | None:
    if not arquivo_path:
        return None
    try:
        resp = (
            supabase.storage
            .from_(STORAGE_BUCKET)
            .create_signed_url(arquivo_path, expires_in)
        )
        if isinstance(resp, dict):
            return (
                resp.get("signedURL")
                or resp.get("signed_url")
                or resp.get("signedUrl")
                or (resp.get("data") or {}).get("signedURL")
                or (resp.get("data") or {}).get("signedUrl")
            )
        return None
    except Exception as e:
        print(f"❌ erro get_anexo_signed_url: {e}")
        return None