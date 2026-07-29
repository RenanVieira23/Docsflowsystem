"""
utils/log_acao.py

Helper central para registrar ações do usuário (criar, editar,
excluir, login, logout, etc.) na tabela `logs`, de qualquer tela do
sistema, sem bloquear a interface.

Uso típico dentro de uma página, logo após uma operação bem-sucedida:

    from utils.log_acao import log_acao

    async def salvar(e):
        ...
        await run_db(page, add_cliente, dados)
        log_acao(page, f"Cadastrou o cliente '{nome}'")
        ...

`log_acao` NÃO precisa de await — ela dispara a gravação em segundo
plano (via page.run_task) e retorna na hora, para não atrasar a ação
principal do usuário por causa de um log.
"""

from __future__ import annotations

import flet as ft


def log_acao(page: ft.Page, acao: str, detalhes: str | None = None):
    """
    Registra uma ação do usuário atual (nivel="acao"). Dispara em
    segundo plano — não bloqueia a tela, e uma falha ao gravar o log
    nunca aparece pro usuário nem interrompe o fluxo principal (a
    própria registrar_log já suprime suas exceções).
    """
    if not hasattr(page, "local_store") or not page.local_store:
        return

    usuario_id = page.local_store.get("usuario_id")
    tenant_id = page.local_store.get("tenant_id")
    if not tenant_id:
        return

    async def _run():
        from database.models import registrar_log
        from database.supabase_client import run_db
        try:
            await run_db(page, registrar_log, usuario_id, acao, detalhes, tenant_id, "acao")
        except Exception:
            # run_db já loga a falha sozinha (nivel="erro"); aqui só
            # evita que a exceção suba e apareça pro usuário.
            pass

    page.run_task(_run)