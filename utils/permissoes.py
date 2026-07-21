"""
utils/permissoes.py

Helper central para checar permissões do usuário logado, por módulo
e ação (ler / cadastrar / editar). As permissões já vêm resolvidas
do login e ficam em page.local_store["permissoes"] — este módulo só
lê essa estrutura, nunca consulta o banco (evita uma query a cada
clique).

Uso típico dentro de uma página:

    from utils.permissoes import pode

    if pode(page, "clientes", "cadastrar"):
        botoes.append(btn_novo_cliente)
"""

from __future__ import annotations

import flet as ft

MODULOS = ["clientes", "contratos", "categorias", "prazos", "partes"]
ACOES = ["ler", "cadastrar", "editar"]


def _is_super(page: ft.Page) -> bool:
    """
    is_global_admin é um super-admin acima do sistema de cargos
    (cross-tenant) — sempre passa em qualquer checagem, igual já
    funcionava antes deste sistema existir.
    """
    if not hasattr(page, "local_store") or not page.local_store:
        return False
    return bool(page.local_store.get("is_global_admin"))


def pode(page: ft.Page, modulo: str, acao: str) -> bool:
    """
    Retorna True se o usuário logado (via seu cargo) pode executar
    `acao` ("ler"/"cadastrar"/"editar") no `modulo`.

    Usuário sem cargo definido (ou sessão sem permissões carregadas)
    NUNCA recebe acesso por padrão — falha fechada, não aberta.
    """
    if _is_super(page):
        return True

    if modulo not in MODULOS or acao not in ACOES:
        return False

    if not hasattr(page, "local_store") or not page.local_store:
        return False

    permissoes = page.local_store.get("permissoes") or {}
    modulo_perm = permissoes.get(modulo) or {}
    chave = {"ler": "pode_ler", "cadastrar": "pode_cadastrar", "editar": "pode_editar"}[acao]
    return bool(modulo_perm.get(chave))


def eh_administrador(page: ft.Page) -> bool:
    """
    Acesso à tela de Administração (gerenciar usuários e cargos) é
    separado do sistema de permissões por módulo — é um cargo
    especial, não um "módulo" com ler/cadastrar/editar.
    """
    if _is_super(page):
        return True
    if not hasattr(page, "local_store") or not page.local_store:
        return False
    if page.local_store.get("is_admin"):
        return True
    return page.local_store.get("cargo_nome") == "Administrador"


def algum_modulo_leitura(page: ft.Page) -> bool:
    """Usado para decidir se o item 'Relatórios' aparece no menu —
    visível se o usuário tem leitura em pelo menos um módulo."""
    if _is_super(page) or eh_administrador(page):
        return True
    return any(pode(page, m, "ler") for m in MODULOS)


def mensagem_sem_permissao(acao: str = "acessar") -> ft.Container:
    """Tela padrão de 'acesso negado', reaproveitável em qualquer rota/página."""
    return ft.Container(
        expand=True,
        alignment=ft.alignment.center,
        content=ft.Column(
            [
                ft.Icon(ft.Icons.LOCK_OUTLINE, size=48, color=ft.Colors.GREY_400),
                ft.Text(
                    f"Você não tem permissão para {acao} este módulo.",
                    size=16, color=ft.Colors.GREY_600,
                ),
                ft.Text(
                    "Fale com um administrador do sistema se precisar de acesso.",
                    size=13, color=ft.Colors.GREY_500,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=8,
        ),
    )