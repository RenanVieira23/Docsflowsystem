"""
pages/erros/view.py
=====================
Telas de erro padronizadas e reutilizáveis para todo o sistema:
  - 404: rota não encontrada
  - 500 / erro genérico: falha inesperada ao renderizar uma tela
  - Sessão expirada: token não pôde ser renovado (ver
    database/supabase_client.py -> SessaoExpiradaError)
  - Falha de conexão: timeout/erro de rede ao falar com o Supabase
  - 403: acesso negado por falta de permissão

ESCOPO: estas telas cobrem falhas na CONSTRUÇÃO de uma tela/rota — o
que acontece de forma síncrona, por isso é capturável em main.py, nas
funções get_view() e on_route_change() — e o carregamento inicial do
sistema.

Erros que ocorrem DEPOIS que uma tela já foi exibida — por exemplo,
durante o carregamento assíncrono de dados disparado via
page.run_task() dentro de uma view (o padrão usado em quase todas as
páginas, ver *_carregar_dados) — continuam sendo tratados
individualmente por cada tela, geralmente com lista vazia e log no
console. Unificar esse segundo tipo de erro com estas mesmas telas
exigiria alterar cada view do sistema — está fora do escopo desta
mudança.
"""

import flet as ft


def _botoes(*botoes: ft.Control) -> ft.Row:
    return ft.Row(
        list(botoes),
        alignment=ft.MainAxisAlignment.CENTER,
        spacing=10,
        wrap=True,
    )


def _tela_base(
    *,
    icone: str,
    cor_icone: str,
    titulo: str,
    mensagem: str,
    acoes: list | None = None,
    codigo: str | None = None,
) -> ft.Container:
    conteudo = [
        ft.Icon(icone, size=52, color=cor_icone),
        ft.Text(titulo, size=20, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER),
        ft.Text(
            mensagem, size=13, color=ft.Colors.GREY_600,
            text_align=ft.TextAlign.CENTER,
        ),
    ]

    if codigo:
        conteudo.append(
            ft.Text(f"Código: {codigo}", size=11, color=ft.Colors.GREY_400)
        )

    if acoes:
        conteudo.append(ft.Container(height=6))
        conteudo.append(_botoes(*acoes))

    return ft.Container(
        expand=True,
        alignment=ft.alignment.center,
        content=ft.Container(
            width=440,
            content=ft.Column(
                conteudo,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=10,
            ),
        ),
    )


def tela_404(page: ft.Page, rota_tentada: str | None = None) -> ft.Container:
    """Rota que não existe no sistema."""

    def _ir_dashboard(e):
        page.go("/dashboard")

    return _tela_base(
        icone=ft.Icons.SEARCH_OFF,
        cor_icone=ft.Colors.BLUE_300,
        titulo="Página não encontrada",
        mensagem=(
            f'O endereço "{rota_tentada}" não existe ou foi movido.'
            if rota_tentada else
            "O endereço acessado não existe ou foi movido."
        ),
        acoes=[ft.FilledButton("Ir para o Dashboard", on_click=_ir_dashboard)],
        codigo="404",
    )


def tela_500(page: ft.Page, rota: str | None = None) -> ft.Container:
    """Falha inesperada ao renderizar uma tela (crash capturado)."""

    def _tentar_novamente(e):
        page.go(rota or "/dashboard")

    def _ir_dashboard(e):
        page.go("/dashboard")

    acoes = [ft.FilledButton("Tentar novamente", on_click=_tentar_novamente)]
    if rota and rota != "/dashboard":
        acoes.append(ft.OutlinedButton("Ir para o Dashboard", on_click=_ir_dashboard))

    return _tela_base(
        icone=ft.Icons.ERROR_OUTLINE,
        cor_icone=ft.Colors.RED_300,
        titulo="Algo deu errado",
        mensagem=(
            "Ocorreu um erro inesperado ao carregar esta página. "
            "O problema já foi registrado. Tente novamente — se persistir, "
            "avise um administrador."
        ),
        acoes=acoes,
        codigo="500",
    )


def tela_conexao(page: ft.Page, rota: str | None = None) -> ft.Container:
    """Falha de conectividade com o servidor (timeout, sem rede, etc.)."""

    def _tentar_novamente(e):
        page.go(rota or "/dashboard")

    return _tela_base(
        icone=ft.Icons.WIFI_OFF,
        cor_icone=ft.Colors.ORANGE_400,
        titulo="Falha de conexão",
        mensagem=(
            "Não foi possível conectar ao servidor. Verifique sua internet "
            "e tente novamente em instantes."
        ),
        acoes=[ft.FilledButton("Tentar novamente", on_click=_tentar_novamente)],
        codigo="CONEXÃO",
    )


def tela_sessao_expirada(page: ft.Page) -> ft.Container:
    """
    Sessão expirada — o token não pôde ser renovado (ver
    database/supabase_client.py -> SessaoExpiradaError). O redirect
    para /login já é disparado de lá mesmo (_finalizar_sessao_expirada);
    esta tela é apenas o conteúdo de transição, com um botão manual
    como rede de segurança caso o redirect automático não conclua.
    """

    def _ir_login(e):
        page.go("/login")

    return _tela_base(
        icone=ft.Icons.LOCK_CLOCK,
        cor_icone=ft.Colors.AMBER_600,
        titulo="Sessão expirada",
        mensagem=(
            "Sua sessão expirou por segurança. Faça login novamente "
            "para continuar."
        ),
        acoes=[ft.FilledButton("Ir para o login", on_click=_ir_login)],
    )


def tela_403(page: ft.Page | None = None, acao: str = "acessar") -> ft.Container:
    """
    Acesso negado por falta de permissão. Substitui/padroniza o antigo
    utils.permissoes.mensagem_sem_permissao — esta versão adiciona um
    botão de retorno quando `page` é informado.
    """
    acoes = []
    if page is not None:
        def _ir_dashboard(e):
            page.go("/dashboard")
        acoes.append(ft.FilledButton("Ir para o Dashboard", on_click=_ir_dashboard))

    return _tela_base(
        icone=ft.Icons.LOCK_OUTLINE,
        cor_icone=ft.Colors.GREY_400,
        titulo="Acesso restrito",
        mensagem=(
            f"Você não tem permissão para {acao} este módulo. "
            "Fale com um administrador do sistema se precisar de acesso."
        ),
        acoes=acoes,
        codigo="403",
    )