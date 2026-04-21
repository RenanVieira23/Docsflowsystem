# database/models.py
import os
import json
import requests
from datetime import datetime, timedelta
from functools import lru_cache
from dotenv import load_dotenv

from database.supabase_client import supabase

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


def _clear_cache():
    _cache_clientes.cache_clear()
    _cache_contratos.cache_clear()


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

def _call(payload):
    try:
        r = requests.post(BASE, json=payload, headers=HEADERS, timeout=20)
        data = r.json()
        if r.status_code != 200 or not data.get("ok"):
            return False, data.get("message")
        return True, data.get("data")
    except Exception as e:
        return False, str(e)

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
# CACHE
# ======================================================

@lru_cache(maxsize=1)
def _cache_clientes():
    resp = _safe_exec(supabase.table("clientes").select("*"), "Erro cache clientes")
    return resp.data if resp else []

@lru_cache(maxsize=1)
def _cache_contratos():
    resp = _safe_exec(supabase.table("contratos").select("*"), "Erro cache contratos")
    return resp.data if resp else []


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

        prof = supabase.table("usuarios").select("*").eq("auth_uid", auth_uid).maybe_single().execute()
        perfil = prof.data if prof else None
        if not perfil:
            return {"_error": "PERFIL_NAO_ENCONTRADO"}

        perfil = _merge_admin_flags(perfil, res.user)
        perfil["_session"] = {
            "access_token": token,
            "refresh_token": res.session.refresh_token,
            "expires_at": res.session.expires_at,
            "auth_uid": auth_uid,
        }
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


# ======================================================
# CLIENTES
# ======================================================

def get_clientes():
    try:
        return list(_cache_clientes())
    except Exception as e:
        print(f"❌ Erro ao buscar clientes: {e}")
        return []

def add_cliente(cliente):
    try:
        data = supabase.table("clientes").insert(cliente).execute()
        _clear_cache()
        if data.data:
            return data.data[0]
    except Exception as e:
        print(f"❌ Erro ao adicionar cliente: {e}")
    return None

def delete_cliente(cliente_id):
    try:
        supabase.table("clientes").delete().eq("id", cliente_id).execute()
        _clear_cache()
    except Exception as e:
        print(f"❌ Erro ao deletar cliente: {e}")

def update_cliente(cliente_id: int, dados: dict):
    try:
        resp = supabase.table("clientes").update(dados).eq("id", cliente_id).execute()
        _clear_cache()
        return resp.data[0] if resp.data else None
    except Exception as e:
        print(f"❌ Erro ao atualizar cliente: {e}")
        return None


# ======================================================
# CONTRATOS
# ======================================================

def get_contratos():
    try:
        return list(_cache_contratos())
    except Exception as e:
        print(f"❌ Erro ao buscar contratos: {e}")
        return []

def get_contratos_por_cliente(cliente_id):
    try:
        data = supabase.table("contratos").select("*").eq("cliente_id", cliente_id).execute()
        return data.data if data.data else []
    except Exception as e:
        print(f"❌ Erro ao buscar contratos do cliente {cliente_id}: {e}")
        return []

def add_contrato(contrato):
    try:
        resp = supabase.table("contratos").insert(contrato).execute()
        _clear_cache()
        if resp.data and len(resp.data) > 0:
            return resp.data[0]
    except Exception as e:
        print(f"❌ Erro ao adicionar contrato: {e}")
    return None

def delete_contrato(contrato_id):
    try:
        supabase.table("contratos").delete().eq("id", contrato_id).execute()
        _clear_cache()
    except Exception as e:
        print(f"❌ Erro ao deletar contrato: {e}")

def update_contrato(contrato_id: int, dados: dict):
    try:
        resp = supabase.table("contratos").update(dados).eq("id", contrato_id).execute()
        _clear_cache()
        return resp.data[0] if resp.data else None
    except Exception as e:
        print(f"❌ Erro ao atualizar contrato: {e}")
        return None


# ======================================================
# PRAZOS
# ======================================================

def add_prazo(contrato_id, meses, observacao, data_criacao, data_vencimento):
    try:
        novo_prazo = {
            "contrato_id": contrato_id,
            "meses": meses or 0,
            "observacao": observacao or "",
            "data_criacao": data_criacao or datetime.now().strftime("%Y-%m-%d"),
            "data_vencimento": data_vencimento,
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
# ======================================================

def add_notificacao(prazo_id, dias_antes=None, data_enviada=None):
    try:
        nova = {
            "prazo_id": prazo_id,
            "dias_antes": dias_antes or 0,
            "data_enviada": data_enviada or datetime.now().strftime("%Y-%m-%d"),
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
# ======================================================

def registrar_log(usuario_id, acao, detalhes=None):
    try:
        novo = {"usuario_id": usuario_id, "acao": acao, "detalhes": detalhes, "data_hora": _now()}
        supabase.table("logs").insert(novo).execute()
    except Exception as e:
        print(f"❌ Erro ao registrar log: {e}")


# ======================================================
# ANEXOS
# ======================================================

def add_anexo(contrato_id, nome_arquivo, arquivo_url=None, arquivo_path=None):
    try:
        novo = {"contrato_id": contrato_id, "nome_arquivo": nome_arquivo, "arquivo_url": arquivo_url, "arquivo_path": arquivo_path}
        resp = supabase.table("anexos").insert(novo).execute()
        return resp.data[0] if resp.data else novo
    except Exception as e:
        print(f"❌ Erro ao adicionar anexo: {e}")
        return None

def get_anexos_por_contrato(contrato_id):
    try:
        resp = supabase.table("anexos").select("*").eq("contrato_id", contrato_id).execute()
        return resp.data if resp.data else []
    except Exception as e:
        print(f"❌ Erro ao buscar anexos: {e}")
        return []


# ======================================================
# DASHBOARD / RELATÓRIOS
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
        """).range(offset, offset+limit-1)
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
        if status == "enviados" and not enviado: continue
        if status == "pendentes" and enviado: continue
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

def criar_usuario_admin(email, senha, usuario, role):
    return _call({"action": "create", "email": email, "password": senha, "usuario": usuario, "role": role})

def atualizar_usuario_admin(user_id, payload):
    return _call({"action": "update", "id": user_id, "usuario": payload["usuario"], "role": payload["role"]})

def deletar_usuario_admin(user_id):
    return _call({"action": "delete", "id": user_id})

# ======================================================
# 👤 PARTES
# ======================================================

def get_partes():
    try:
        resp = _safe_exec(
            supabase.table("partes").select("*").order("nome"),
            "Erro partes"
        )
        return resp.data if resp else []
    except Exception as e:
        print(f"❌ Erro ao buscar partes: {e}")
        return []


def add_parte(parte: dict):
    try:
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
# ======================================================

def get_tipos_partes():
    try:
        resp = _safe_exec(
            supabase.table("tipos_partes").select("*").order("nome"),
            "Erro tipos_partes"
        )
        return resp.data if resp else []
    except Exception as e:
        print(f"❌ Erro ao buscar tipos de partes: {e}")
        return []


def add_tipo_parte(nome: str):
    try:
        resp = supabase.table("tipos_partes").insert({"nome": nome.strip()}).execute()
        return resp.data[0] if resp.data else None
    except Exception as e:
        print(f"❌ Erro ao adicionar tipo de parte: {e}")
        return None


def update_tipo_parte(tipo_id: int, dados: dict):
    try:
        resp = (
            supabase.table("tipos_partes")
            .update(dados)
            .eq("id", tipo_id)
            .execute()
        )
        return resp.data[0] if resp.data else None
    except Exception as e:
        print(f"❌ Erro ao atualizar tipo de parte: {e}")
        return None


def delete_tipo_parte(tipo_id: int):
    try:
        supabase.table("tipos_partes").delete().eq("id", tipo_id).execute()
        return True
    except Exception as e:
        print(f"❌ Erro ao deletar tipo de parte: {e}")
        return False


# ======================================================
# 🔗 CONTRATO_PARTES
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

def add_contrato_parte(contrato_id: int, parte_id: int, tipo_vinculo: str):
    try:
        payload = {
            "contrato_id": contrato_id,
            "parte_id": parte_id,
            "tipo_vinculo": tipo_vinculo,
        }
        resp = supabase.table("contrato_partes").insert(payload).execute()
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
# 👥 GESTÃO DE USUÁRIOS (admin do tenant)
# ======================================================

from database.supabase_client import supabase_admin


def get_usuarios_do_tenant(tenant_id: str) -> list:
    """Lista todos os usuários do tenant — usa supabase_admin para bypassar RLS."""
    try:
        client = supabase_admin if supabase_admin else supabase
        resp = (
            client.table("usuarios")
            .select("*")
            .eq("tenant_id", tenant_id)
            .order("usuario")
            .execute()
        )
        return resp.data if resp.data else []
    except Exception as e:
        print(f"❌ Erro ao listar usuários: {e}")
        return []


def get_usuarios() -> list:
    """Lista todos os usuários (sem filtro de tenant)."""
    try:
        resp = (
            supabase.table("usuarios")
            .select("*")
            .order("usuario")
            .execute()
        )
        return resp.data if resp.data else []
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
        return {"_error": "SUPABASE_SERVICE_KEY não configurada no .env"}

    email = email.strip().lower()
    nome_usuario = nome_usuario.strip()

    try:
        # 1️⃣ cria no AUTH
        res = supabase_admin.auth.admin.create_user({
            "email": email,
            "password": senha,
            "email_confirm": True,
            "user_metadata": {"display_name": nome_usuario},
        })

        auth_uid = str(res.user.id)

        # 2️⃣ cria perfil (AGORA CORRETO)
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

        return resp.data[0]

    except Exception as e:
        try:
            supabase_admin.auth.admin.delete_user(auth_uid)
        except:
            pass

        return {"_error": str(e)}


def update_usuario_admin(usuario_id: int, dados: dict) -> dict:
    """
    Atualiza nome/role/is_admin na tabela usuarios.
    Se 'senha' estiver em dados, atualiza também no Auth.
    """
    senha = dados.pop("senha", None)

    try:
        resp = (
            supabase.table("usuarios")
            .update(dados)
            .eq("id", usuario_id)
            .execute()
        )
        perfil = resp.data[0] if resp.data else {}
    except Exception as e:
        return {"_error": str(e)}

    # Atualiza senha no Auth se fornecida
    if senha and perfil.get("auth_uid") and supabase_admin:
        try:
            supabase_admin.auth.admin.update_user_by_id(
                perfil["auth_uid"],
                {"password": senha},
            )
        except Exception as e:
            print(f"⚠️  Perfil atualizado mas senha não alterada: {e}")

    return perfil


def delete_usuario_admin(usuario_id: int) -> bool:
    """
    Remove o usuário da tabela usuarios e do Supabase Auth.
    """
    try:
        # Busca auth_uid antes de deletar
        resp = (
            supabase.table("usuarios")
            .select("auth_uid")
            .eq("id", usuario_id)
            .maybe_single()
            .execute()
        )
        auth_uid = (resp.data or {}).get("auth_uid")

        # Remove da tabela
        supabase.table("usuarios").delete().eq("id", usuario_id).execute()

        # Remove do Auth
        if auth_uid and supabase_admin:
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


def add_vinculo(tipo: str, tenant_id: str) -> dict:
    try:
        resp = supabase.table("vinculos").insert({"tipo": tipo.strip(), "tenant_id": tenant_id}).execute()
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


# ======================================================
# 📄 TIPOS DE CONTRATOS
# ======================================================

def get_tipos_contratos(tenant_id: str = None) -> list:
    try:
        q = supabase.table("tipos_contratos").select("*")
        if tenant_id:
            q = q.eq("tenant_id", tenant_id)
        resp = q.order("nome").execute()
        return resp.data if resp.data else []
    except Exception as e:
        print(f"❌ Erro ao buscar tipos de contratos: {e}")
        return []


def add_tipo_contrato_db(nome: str, tenant_id: str) -> dict:
    try:
        resp = supabase.table("tipos_contratos").insert({"nome": nome.strip(), "tenant_id": tenant_id}).execute()
        return resp.data[0] if resp.data else {}
    except Exception as e:
        print(f"❌ Erro ao adicionar tipo de contrato: {e}")
        return {"_error": str(e)}


def delete_tipo_contrato_db(tipo_id: int) -> bool:
    try:
        supabase.table("tipos_contratos").delete().eq("id", tipo_id).execute()
        return True
    except Exception as e:
        print(f"❌ Erro ao deletar tipo de contrato: {e}")
        return False


# ======================================================
# ⏰ TIPOS DE PRAZOS
# ======================================================

def get_tipos_prazos_db(tenant_id: str = None) -> list:
    try:
        q = supabase.table("tipos_prazos").select("*")
        if tenant_id:
            q = q.eq("tenant_id", tenant_id)
        resp = q.order("nome").execute()
        return resp.data if resp.data else []
    except Exception as e:
        print(f"❌ Erro ao buscar tipos de prazos: {e}")
        return []


def add_tipo_prazo_db(nome: str, tenant_id: str) -> dict:
    try:
        resp = supabase.table("tipos_prazos").insert({"nome": nome.strip(), "tenant_id": tenant_id}).execute()
        return resp.data[0] if resp.data else {}
    except Exception as e:
        print(f"❌ Erro ao adicionar tipo de prazo: {e}")
        return {"_error": str(e)}


def delete_tipo_prazo_db(tipo_id: int) -> bool:
    try:
        supabase.table("tipos_prazos").delete().eq("id", tipo_id).execute()
        return True
    except Exception as e:
        print(f"❌ Erro ao deletar tipo de prazo: {e}")
        return False


# ======================================================
# STORAGE — ANEXOS
# ======================================================
STORAGE_BUCKET = "contratos"


def _guess_mime(filename: str) -> str:
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    mimes = {
        "pdf": "application/pdf",
        "doc": "application/msword",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xls": "application/vnd.ms-excel",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "gif": "image/gif", "webp": "image/webp",
        "txt": "text/plain", "csv": "text/csv",
        "zip": "application/zip",
    }
    return mimes.get(ext, "application/octet-stream")


def upload_anexo(contrato_id: int, nome_arquivo: str, file_bytes: bytes):
    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        storage_path = f"contratos/{contrato_id}/{ts}_{nome_arquivo}"
        supabase.storage.from_(STORAGE_BUCKET).upload(
            storage_path, file_bytes,
            {"content-type": _guess_mime(nome_arquivo), "upsert": "false"},
        )
        url = supabase.storage.from_(STORAGE_BUCKET).get_public_url(storage_path)
        return add_anexo(contrato_id=contrato_id, nome_arquivo=nome_arquivo,
                         arquivo_url=url, arquivo_path=storage_path)
    except Exception as e:
        print(f"❌ Erro ao fazer upload de anexo: {e}")
        return None


def delete_anexo(anexo_id: int, arquivo_path: str = None) -> bool:
    try:
        if arquivo_path:
            try:
                supabase.storage.from_(STORAGE_BUCKET).remove([arquivo_path])
            except Exception as se:
                print(f"⚠️  Storage remove falhou (ignorado): {se}")
        supabase.table("anexos").delete().eq("id", anexo_id).execute()
        return True
    except Exception as e:
        print(f"❌ Erro ao deletar anexo: {e}")
        return False