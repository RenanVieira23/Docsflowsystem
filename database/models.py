# database/models.py
import os
import re
import json
import threading
import time as _time
import requests
from datetime import datetime, timedelta
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

    try:
        supabase.postgrest.auth(token)
    except Exception as e:
        print(f"❌ Erro ao aplicar token no postgrest: {e}")

    try:
        if hasattr(supabase, "storage") and hasattr(supabase.storage, "_client"):
            supabase.storage._client.headers.update({"Authorization": f"Bearer {token}"})
    except Exception as e:
        print(f"⚠️ Aviso: não foi possível aplicar token no storage client: {e}")

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
# FIX (item 9 — bug de invalidação): a versão anterior usava
# @lru_cache e _clear_cache() chamava .cache_clear() em TODO o cache,
# derrubando os dados de TODOS os tenants sempre que qualquer um
# deles salvava um cliente ou contrato — efeito colateral não
# intencional em produção multi-tenant (um tenant grande salvando com
# frequência faria os outros tenants recarregarem do banco toda hora).
# Trocado por um dict simples com invalidação por chave (tenant_id),
# então salvar dados de um tenant só invalida o cache DESSE tenant.

_cache_lock = threading.Lock()
_cache_clientes_store: dict[str, list] = {}
_cache_contratos_store: dict[str, list] = {}


def _cache_clientes(tenant_id: str) -> list:
    with _cache_lock:
        if tenant_id in _cache_clientes_store:
            return _cache_clientes_store[tenant_id]

    try:
        resp = _safe_exec(
            supabase.table("clientes").select("*").eq("tenant_id", tenant_id),
            "Erro cache clientes"
        )
        dados = resp.data if resp else []
    except Exception as e:
        print(f"❌ erro cache clientes: {e}")
        dados = []

    with _cache_lock:
        _cache_clientes_store[tenant_id] = dados
    return dados


def _cache_contratos(tenant_id: str) -> list:
    with _cache_lock:
        if tenant_id in _cache_contratos_store:
            return _cache_contratos_store[tenant_id]

    try:
        resp = _safe_exec(
            supabase.table("contratos").select("*").eq("tenant_id", tenant_id),
            "Erro cache contratos"
        )
        dados = resp.data if resp else []
    except Exception as e:
        print(f"❌ erro cache contratos: {e}")
        dados = []

    with _cache_lock:
        _cache_contratos_store[tenant_id] = dados
    return dados


def _clear_cache(tenant_id: str | None = None):
    """
    Invalida o cache de clientes/contratos. Se `tenant_id` for
    informado, limpa só os dados DESSE tenant (comportamento padrão
    esperado ao salvar/editar/excluir). Sem tenant_id, limpa tudo —
    usado apenas como rede de segurança em chamadas legadas que ainda
    não repassam o tenant.
    """
    with _cache_lock:
        if tenant_id:
            _cache_clientes_store.pop(tenant_id, None)
            _cache_contratos_store.pop(tenant_id, None)
        else:
            _cache_clientes_store.clear()
            _cache_contratos_store.clear()


# ======================================================
# 🛡️ RATE LIMITING — proteção contra força bruta
# ======================================================
# LIMITAÇÃO CONHECIDA: vive em memória do processo — válido para uma
# única instância. Ver database/supabase_client.py para o mesmo tipo
# de observação.

_MAX_TENTATIVAS_LOGIN = 5
_JANELA_BLOQUEIO_LOGIN_SEG = 15 * 60

_MAX_SOLICITACOES_RESET = 3
_JANELA_BLOQUEIO_RESET_SEG = 60 * 60

_tentativas: dict[str, list[float]] = {}
_lock_tentativas = threading.Lock()


def _registrar_tentativa(chave: str, janela_seg: int):
    agora = _time.time()
    with _lock_tentativas:
        historico = _tentativas.setdefault(chave, [])
        historico.append(agora)
        _tentativas[chave] = [t for t in historico if agora - t < janela_seg]


def _limpar_tentativas(chave: str):
    with _lock_tentativas:
        _tentativas.pop(chave, None)


def _esta_bloqueado(chave: str, limite: int, janela_seg: int) -> tuple[bool, int]:
    agora = _time.time()
    with _lock_tentativas:
        historico = [t for t in _tentativas.get(chave, []) if agora - t < janela_seg]
        _tentativas[chave] = historico
        if len(historico) >= limite:
            mais_antiga = min(historico)
            restante = int(janela_seg - (agora - mais_antiga))
            return True, max(restante, 1)
        return False, 0


# ======================================================
# 🔑 SESSÕES TEMPORÁRIAS DE RECUPERAÇÃO DE SENHA
# ======================================================

_JANELA_SESSAO_RECUPERACAO_SEG = 10 * 60

_sessoes_recuperacao: dict[str, dict] = {}
_lock_sessoes_recuperacao = threading.Lock()


def _salvar_sessao_recuperacao(email: str, access_token: str, refresh_token: str | None):
    with _lock_sessoes_recuperacao:
        _sessoes_recuperacao[email] = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expira_em": _time.time() + _JANELA_SESSAO_RECUPERACAO_SEG,
        }


def _obter_sessao_recuperacao(email: str) -> dict | None:
    with _lock_sessoes_recuperacao:
        sessao = _sessoes_recuperacao.get(email)
        if not sessao:
            return None
        if _time.time() > sessao["expira_em"]:
            _sessoes_recuperacao.pop(email, None)
            return None
        return sessao


def _limpar_sessao_recuperacao(email: str):
    with _lock_sessoes_recuperacao:
        _sessoes_recuperacao.pop(email, None)


# ======================================================
# AUTH + PERFIL
# ======================================================

def autenticar_usuario(email: str, senha: str):
    email_norm = (email or "").strip().lower()
    chave = f"login:{email_norm}"

    bloqueado, restante = _esta_bloqueado(chave, _MAX_TENTATIVAS_LOGIN, _JANELA_BLOQUEIO_LOGIN_SEG)
    if bloqueado:
        minutos = max(1, restante // 60)
        print(f"🚫 Login bloqueado por excesso de tentativas: {email_norm}")
        return {"_error": f"Muitas tentativas incorretas. Tente novamente em {minutos} minuto(s)."}

    try:
        res = supabase.auth.sign_in_with_password({
            "email": email_norm,
            "password": (senha or "").strip(),
        })

        if not res or not getattr(res, "session", None) or not getattr(res, "user", None):
            _registrar_tentativa(chave, _JANELA_BLOQUEIO_LOGIN_SEG)
            return None

        _limpar_tentativas(chave)

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

        cargo_nome = None
        cargo_id = perfil.get("cargo_id")
        if cargo_id:
            cargo_resp = (
                supabase.table("cargos").select("nome")
                .eq("id", cargo_id).maybe_single().execute()
            )
            if cargo_resp and cargo_resp.data:
                cargo_nome = cargo_resp.data.get("nome")

        perfil["cargo_nome"] = cargo_nome
        perfil["permissoes"] = get_permissoes_usuario(perfil)

        perfil["_session"] = {
            "access_token": token,
            "refresh_token": res.session.refresh_token,
            "expires_at": res.session.expires_at,
            "auth_uid": auth_uid,
        }

        perfil["tenant_nome"] = tenant_nome

        return perfil

    except Exception as e:
        _registrar_tentativa(chave, _JANELA_BLOQUEIO_LOGIN_SEG)
        print(f"❌ Erro ao autenticar/buscar perfil: {e}")
        return None


# ======================================================
# 🔑 RECUPERAÇÃO DE SENHA
# ======================================================

def solicitar_redefinicao_senha(email: str) -> dict:
    email_norm = (email or "").strip().lower()
    if not email_norm:
        return {"_error": "Informe um e-mail."}

    chave = f"reset:{email_norm}"
    bloqueado, restante = _esta_bloqueado(chave, _MAX_SOLICITACOES_RESET, _JANELA_BLOQUEIO_RESET_SEG)
    if bloqueado:
        minutos = max(1, restante // 60)
        return {"_error": f"Muitas solicitações. Tente novamente em {minutos} minuto(s)."}

    _registrar_tentativa(chave, _JANELA_BLOQUEIO_RESET_SEG)
    _limpar_sessao_recuperacao(email_norm)

    try:
        supabase.auth.reset_password_email(email_norm)
    except Exception as e:
        print(f"❌ Erro ao solicitar redefinição de senha ({email_norm}): {e}")

    return {"ok": True}


def confirmar_redefinicao_senha(email: str, codigo: str, nova_senha: str) -> dict:
    email_norm = (email or "").strip().lower()
    codigo = (codigo or "").strip()
    nova_senha = (nova_senha or "").strip()

    if not email_norm or not nova_senha:
        return {"_error": "Preencha todos os campos."}
    if len(nova_senha) < 6:
        return {"_error": "A nova senha deve ter ao menos 6 caracteres."}

    sessao_cache = _obter_sessao_recuperacao(email_norm)

    try:
        if sessao_cache:
            token = sessao_cache["access_token"]
        else:
            if not codigo:
                return {"_error": "Informe o código recebido por e-mail."}

            res = supabase.auth.verify_otp({
                "email": email_norm,
                "token": codigo,
                "type": "recovery",
            })

            if not res or not getattr(res, "session", None):
                return {"_error": "Código inválido ou expirado. Solicite um novo código."}

            token = res.session.access_token
            _salvar_sessao_recuperacao(
                email_norm, token, getattr(res.session, "refresh_token", None)
            )

        _apply_access_token(token)
        supabase.auth.update_user({"password": nova_senha})

        _limpar_sessao_recuperacao(email_norm)
        try:
            supabase.auth.sign_out()
        except Exception:
            pass

        return {"ok": True}

    except Exception as e:
        msg = str(e)
        msg_lower = msg.lower()
        print(f"❌ Erro ao confirmar redefinição de senha ({email_norm}): {e}")

        if "different from the old password" in msg_lower or "should be different" in msg_lower:
            return {
                "_error": (
                    "A nova senha deve ser diferente da senha atual. "
                    "Escolha outra senha e clique em Redefinir novamente "
                    "— não é necessário pedir um novo código."
                )
            }

        if "expired" in msg_lower or "invalid" in msg_lower or "token" in msg_lower:
            _limpar_sessao_recuperacao(email_norm)
            return {"_error": "Código inválido ou expirado. Solicite um novo código."}

        return {"_error": "Não foi possível redefinir a senha. Tente novamente."}


# ======================================================
# 📜 TERMOS DE USO / POLÍTICA DE PRIVACIDADE (LGPD)
# ======================================================

def registrar_aceite_termos(usuario_id: int, versao: str) -> dict:
    try:
        client = supabase_admin or supabase
        resp = (
            client.table("usuarios")
            .update({
                "termos_aceitos_em": _now(),
                "termos_versao": versao,
            })
            .eq("id", usuario_id)
            .execute()
        )
        return resp.data[0] if resp.data else {"_error": "Usuário não encontrado."}
    except Exception as e:
        print(f"❌ Erro ao registrar aceite dos termos: {e}")
        return {"_error": str(e)}


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
            _clear_cache(tenant_id)
        return list(_cache_clientes(tenant_id))
    except Exception as e:
        print(f"❌ erro clientes: {e}")
        return []


def add_cliente(cliente: dict):
    try:
        if "tenant_id" not in cliente:
            raise Exception("tenant_id obrigatório")
        data = supabase.table("clientes").insert(cliente).execute()
        _clear_cache(cliente["tenant_id"])
        return data.data[0] if data.data else None
    except Exception as e:
        print(f"❌ erro add cliente: {e}")
        return None


def delete_cliente(cliente_id: int):
    """Não usado pela UI — exclusão visível é sempre soft delete via
    update_cliente({"ativo": False}). Ver pages/clientes/view.py."""
    try:
        supabase.table("clientes").delete().eq("id", cliente_id).execute()
        _clear_cache()
    except Exception as e:
        print(f"❌ erro delete cliente: {e}")


def update_cliente(cliente_id: int, dados: dict, tenant_id: str | None = None):
    try:
        resp = (
            supabase.table("clientes")
            .update(dados)
            .eq("id", cliente_id)
            .execute()
        )
        cliente_atualizado = resp.data[0] if resp.data else None
        _clear_cache(tenant_id or (cliente_atualizado or {}).get("tenant_id"))
        return cliente_atualizado
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
        _clear_cache(contrato["tenant_id"])
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


def update_contrato(contrato_id: int, dados: dict, tenant_id: str | None = None):
    try:
        resp = (
            supabase.table("contratos")
            .update(dados)
            .eq("id", contrato_id)
            .execute()
        )
        contrato_atualizado = resp.data[0] if resp.data else None
        _clear_cache(tenant_id or (contrato_atualizado or {}).get("tenant_id"))
        return contrato_atualizado
    except Exception as e:
        print(f"❌ Erro ao atualizar contrato: {e}")
        return None


# ======================================================
# PRAZOS
# ======================================================

def add_prazo(contrato_id, meses, observacao, data_criacao, data_vencimento, tenant_id, tipo=None):
    try:
        novo_prazo = {
            "contrato_id": contrato_id,
            "meses": meses or 0,
            "observacao": observacao or "",
            "data_criacao": data_criacao or datetime.now().strftime("%Y-%m-%d"),
            "data_vencimento": data_vencimento,
            "tenant_id": tenant_id,
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
# ======================================================

def add_notificacao(prazo_id, tenant_id: str, dias_antes=None, data_enviada=None):
    try:
        if not tenant_id:
            raise Exception("tenant_id obrigatório em add_notificacao")
        nova = {
            "prazo_id": prazo_id,
            "dias_antes": dias_antes or 0,
            "data_enviada": data_enviada or datetime.now().strftime("%Y-%m-%d"),
            "tenant_id": tenant_id,
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

def registrar_log(usuario_id, acao, detalhes=None, tenant_id=None, nivel="acao"):
    try:
        if not tenant_id:
            print(f"⚠️ registrar_log: tenant_id não fornecido, log ignorado (acao={acao})")
            return
        novo = {
            "usuario_id": usuario_id,
            "acao": acao,
            "detalhes": detalhes,
            "data_hora": _now(),
            "tenant_id": tenant_id,
            "nivel": nivel,
        }
        try:
            supabase.table("logs").insert(novo).execute()
        except Exception as e:
            if "PGRST204" in str(e) or "nivel" in str(e):
                print("⚠️ Coluna 'nivel' ainda não existe em 'logs' — "
                      "rode sql/2026-07_logs_nivel.sql. Gravando sem nivel por enquanto.")
                novo.pop("nivel", None)
                supabase.table("logs").insert(novo).execute()
            else:
                raise
    except Exception as e:
        print(f"❌ Erro ao registrar log: {e}")


def registrar_log_erro(tenant_id, usuario_id, contexto: str, erro: str):
    try:
        client = supabase_admin or supabase
        payload = {
            "usuario_id": usuario_id,
            "acao": contexto,
            "detalhes": (erro or "")[:2000],
            "data_hora": _now(),
            "tenant_id": tenant_id,
            "nivel": "erro",
        }
        try:
            client.table("logs").insert(payload).execute()
        except Exception as e:
            if "PGRST204" in str(e) or "nivel" in str(e):
                payload.pop("nivel", None)
                client.table("logs").insert(payload).execute()
            else:
                raise
    except Exception as e:
        print(f"❌ Também falhou ao registrar o erro acima no banco: {e}")


def get_logs(
    tenant_id: str,
    nivel: str | None = None,
    usuario_id: int | None = None,
    busca: str | None = None,
    limit: int = 25,
    offset: int = 0,
) -> tuple[list, int]:
    """
    Lista de logs de auditoria do tenant, paginada no banco (não
    carrega tudo em memória — tabela de logs cresce indefinidamente).
    Usada por pages/logs/view.py. Retorna (linhas, total_de_registros).

    Filtros opcionais: nivel ("acao"/"erro"/"sistema"), usuario_id,
    busca (texto contido no campo "acao").
    """
    try:
        q = (
            supabase.table("logs")
            .select("*", count="exact")
            .eq("tenant_id", tenant_id)
        )
        if nivel and nivel != "todos":
            q = q.eq("nivel", nivel)
        if usuario_id:
            q = q.eq("usuario_id", usuario_id)
        if busca:
            q = q.ilike("acao", f"%{busca}%")

        q = q.order("data_hora", desc=True).range(offset, offset + limit - 1)
        resp = q.execute()
        return resp.data or [], (resp.count or 0)
    except Exception as e:
        print(f"❌ Erro ao buscar logs: {e}")
        return [], 0


# ======================================================
# ANEXOS
# ======================================================

def add_anexo(contrato_id, nome_arquivo, tenant_id: str, arquivo_url=None, arquivo_path=None):
    try:
        if not tenant_id:
            raise Exception("tenant_id obrigatório em add_anexo")
        novo = {
            "contrato_id": contrato_id,
            "nome_arquivo": nome_arquivo,
            "arquivo_url": arquivo_url,
            "arquivo_path": arquivo_path,
            "tenant_id": tenant_id,
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
# ======================================================

def get_nomes_partes_por_contrato(tenant_id: str) -> dict:
    try:
        resp = (
            supabase.table("contrato_partes")
            .select("contrato_id, partes!inner(nome), contratos!inner(tenant_id)")
            .eq("contratos.tenant_id", tenant_id)
            .execute()
        )
        agrupado: dict[int, list[str]] = {}
        for row in (resp.data or []):
            cid = row.get("contrato_id")
            nome = (row.get("partes") or {}).get("nome", "")
            if not cid or not nome:
                continue
            agrupado.setdefault(cid, []).append(nome)

        return {cid: ", ".join(nomes) for cid, nomes in agrupado.items()}
    except Exception as e:
        print(f"❌ Erro ao buscar partes por contrato: {e}")
        return {}


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
    try:
        if not tenant_id:
            raise Exception("tenant_id obrigatório em add_contrato_parte")
        payload = {
            "contrato_id": contrato_id,
            "parte_id": parte_id,
            "tipo_vinculo": tipo_vinculo,
            "tenant_id": tenant_id,
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


def update_contrato_parte(cp_id: int, parte_id: int, tipo_vinculo: str):
    try:
        resp = (
            supabase.table("contrato_partes")
            .update({"parte_id": parte_id, "tipo_vinculo": tipo_vinculo})
            .eq("id", cp_id)
            .execute()
        )
        return resp.data[0] if resp.data else None
    except Exception as e:
        print(f"❌ Erro ao atualizar parte do contrato: {e}")
        return None


# ======================================================
# 👥 GESTÃO DE USUÁRIOS (sempre via supabase_admin)
# ======================================================

def get_usuarios_do_tenant(tenant_id: str) -> list:
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
    cargo_id: int | None = None,
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
            "cargo_id": cargo_id,
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


def update_usuario_admin(usuario_id: int, dados: dict, tenant_id: str) -> dict:
    if not tenant_id:
        return {"_error": "tenant_id obrigatório."}

    senha = dados.pop("senha", None)

    try:
        resp = (
            supabase_admin
            .table("usuarios")
            .update(dados)
            .eq("id", usuario_id)
            .eq("tenant_id", tenant_id)
            .execute()
        )
        perfil = resp.data[0] if resp.data else None
        if not perfil:
            return {"_error": "Usuário não encontrado neste tenant."}
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


def delete_usuario_admin(usuario_id: int, tenant_id: str) -> bool:
    if not tenant_id:
        print("❌ delete_usuario_admin chamado sem tenant_id — operação recusada.")
        return False

    try:
        resp = (
            supabase_admin
            .table("usuarios")
            .select("auth_uid")
            .eq("id", usuario_id)
            .eq("tenant_id", tenant_id)
            .maybe_single()
            .execute()
        )

        if not resp or not resp.data:
            print(f"❌ delete_usuario_admin: usuário {usuario_id} não pertence ao tenant {tenant_id}.")
            return False

        auth_uid = resp.data.get("auth_uid")

        supabase_admin.table("usuarios") \
            .delete() \
            .eq("id", usuario_id) \
            .eq("tenant_id", tenant_id) \
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
# ======================================================

def get_tipos_contratos(tenant_id: str = None):
    try:
        q = supabase.table("tipos_contratos").select("*").order("nome")
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


# ======================================================
# 🔐 CARGOS E PERMISSÕES
# ======================================================

MODULOS_PERMISSAO = ["clientes", "contratos", "categorias", "prazos", "partes"]


def get_cargos(tenant_id: str) -> list:
    try:
        resp = _safe_exec(
            supabase.table("cargos")
            .select("*")
            .eq("tenant_id", tenant_id)
            .order("padrao", desc=True)
            .order("nome"),
            "Erro cargos",
        )
        return resp.data if resp else []
    except Exception as e:
        print(f"❌ Erro ao buscar cargos: {e}")
        return []


def get_cargo_permissoes(cargo_id: int) -> dict:
    try:
        resp = _safe_exec(
            supabase.table("cargo_permissoes").select("*").eq("cargo_id", cargo_id),
            "Erro cargo_permissoes",
        )
        linhas = resp.data if resp else []
        mapa = {m: {"pode_ler": False, "pode_cadastrar": False, "pode_editar": False, "pode_excluir": False}
                for m in MODULOS_PERMISSAO}
        for linha in linhas:
            mapa[linha["modulo"]] = {
                "pode_ler": bool(linha.get("pode_ler")),
                "pode_cadastrar": bool(linha.get("pode_cadastrar")),
                "pode_editar": bool(linha.get("pode_editar")),
                "pode_excluir": bool(linha.get("pode_excluir")),
            }
        return mapa
    except Exception as e:
        print(f"❌ Erro ao buscar permissões do cargo: {e}")
        return {m: {"pode_ler": False, "pode_cadastrar": False, "pode_editar": False, "pode_excluir": False}
                for m in MODULOS_PERMISSAO}


def get_permissoes_usuario(usuario: dict) -> dict:
    cargo_id = usuario.get("cargo_id")
    if not cargo_id:
        return {m: {"pode_ler": False, "pode_cadastrar": False, "pode_editar": False, "pode_excluir": False}
                for m in MODULOS_PERMISSAO}
    return get_cargo_permissoes(cargo_id)


def _cargo_pertence_ao_tenant(cargo_id: int, tenant_id: str) -> bool:
    try:
        resp = (
            supabase_admin.table("cargos")
            .select("id")
            .eq("id", cargo_id)
            .eq("tenant_id", tenant_id)
            .maybe_single()
            .execute()
        )
        return bool(resp and resp.data)
    except Exception as e:
        print(f"❌ Erro ao validar tenant do cargo {cargo_id}: {e}")
        return False


def add_cargo(tenant_id: str, nome: str) -> dict:
    try:
        if not (nome or "").strip():
            return {"_error": "Nome do cargo é obrigatório."}

        resp = (
            supabase_admin.table("cargos")
            .insert({"tenant_id": tenant_id, "nome": nome.strip(), "padrao": False})
            .execute()
        )
        cargo = resp.data[0] if resp.data else None
        if not cargo:
            return {"_error": "Não foi possível criar o cargo."}

        supabase_admin.table("cargo_permissoes").insert([
            {"cargo_id": cargo["id"], "modulo": m,
             "pode_ler": False, "pode_cadastrar": False, "pode_editar": False, "pode_excluir": False}
            for m in MODULOS_PERMISSAO
        ]).execute()

        return cargo
    except Exception as e:
        msg = str(e)
        if "duplicate key" in msg or "unique" in msg.lower():
            return {"_error": "Já existe um cargo com esse nome."}
        print(f"❌ Erro ao criar cargo: {e}")
        return {"_error": msg}


def update_cargo_nome(cargo_id: int, nome: str, tenant_id: str) -> dict:
    if not tenant_id:
        return {"_error": "tenant_id obrigatório."}
    if not _cargo_pertence_ao_tenant(cargo_id, tenant_id):
        return {"_error": "Cargo não encontrado neste tenant."}

    try:
        if not (nome or "").strip():
            return {"_error": "Nome do cargo é obrigatório."}
        resp = (
            supabase_admin.table("cargos")
            .update({"nome": nome.strip()})
            .eq("id", cargo_id)
            .eq("tenant_id", tenant_id)
            .execute()
        )
        return resp.data[0] if resp.data else {"_error": "Cargo não encontrado."}
    except Exception as e:
        msg = str(e)
        if "duplicate key" in msg or "unique" in msg.lower():
            return {"_error": "Já existe um cargo com esse nome."}
        print(f"❌ Erro ao renomear cargo: {e}")
        return {"_error": msg}


def delete_cargo(cargo_id: int, tenant_id: str) -> dict:
    if not tenant_id:
        return {"_error": "tenant_id obrigatório."}

    try:
        cargo = (
            supabase_admin.table("cargos").select("*")
            .eq("id", cargo_id).eq("tenant_id", tenant_id)
            .maybe_single().execute()
        )
        cargo = cargo.data if cargo else None
        if not cargo:
            return {"_error": "Cargo não encontrado neste tenant."}
        if cargo.get("padrao"):
            return {"_error": "Cargos padrão (Leitor, Executor, Administrador) não podem ser excluídos."}

        vinculados = (
            supabase_admin.table("usuarios").select("id", count="exact")
            .eq("cargo_id", cargo_id).execute()
        )
        total_vinculados = vinculados.count if vinculados and vinculados.count is not None else len(vinculados.data or [])
        if total_vinculados:
            return {"_error": f"Existem {total_vinculados} usuário(s) com este cargo. Mude o cargo deles antes de excluir."}

        supabase_admin.table("cargos").delete().eq("id", cargo_id).eq("tenant_id", tenant_id).execute()
        return {"ok": True}
    except Exception as e:
        print(f"❌ Erro ao excluir cargo: {e}")
        return {"_error": str(e)}


def set_permissao_cargo(
    cargo_id: int, modulo: str,
    pode_ler: bool, pode_cadastrar: bool, pode_editar: bool, pode_excluir: bool,
    tenant_id: str,
) -> dict:
    if not tenant_id:
        return {"_error": "tenant_id obrigatório."}
    if not _cargo_pertence_ao_tenant(cargo_id, tenant_id):
        return {"_error": "Cargo não encontrado neste tenant."}

    try:
        if modulo not in MODULOS_PERMISSAO:
            return {"_error": f"Módulo inválido: {modulo}"}

        pode_ler = pode_ler or pode_cadastrar or pode_editar or pode_excluir

        resp = (
            supabase_admin.table("cargo_permissoes")
            .upsert({
                "cargo_id": cargo_id,
                "modulo": modulo,
                "pode_ler": pode_ler,
                "pode_cadastrar": pode_cadastrar,
                "pode_editar": pode_editar,
                "pode_excluir": pode_excluir,
            }, on_conflict="cargo_id,modulo")
            .execute()
        )
        return resp.data[0] if resp.data else {"_error": "Não foi possível salvar a permissão."}
    except Exception as e:
        print(f"❌ Erro ao salvar permissão: {e}")
        return {"_error": str(e)}


def update_usuario_cargo(usuario_id: int, cargo_id: int, tenant_id: str) -> dict:
    if not tenant_id:
        return {"_error": "tenant_id obrigatório."}
    if not _cargo_pertence_ao_tenant(cargo_id, tenant_id):
        return {"_error": "Cargo não encontrado neste tenant."}

    try:
        resp = (
            supabase_admin.table("usuarios")
            .update({"cargo_id": cargo_id})
            .eq("id", usuario_id)
            .eq("tenant_id", tenant_id)
            .execute()
        )
        return resp.data[0] if resp.data else {"_error": "Usuário não encontrado neste tenant."}
    except Exception as e:
        print(f"❌ Erro ao vincular cargo ao usuário: {e}")
        return {"_error": str(e)}