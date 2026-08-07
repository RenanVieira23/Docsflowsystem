"""
pages/termos/view.py
=====================
Diálogo de Termos de Uso / Política de Privacidade.

Dois modos:
  - "leitura": qualquer pessoa pode abrir a qualquer momento (link na
    tela de login, item no menu lateral). Só tem botão "Fechar".
  - "aceite": modo obrigatório, usado no login quando o usuário ainda
    não aceitou a versão vigente dos termos (ver utils/termos.py).
    Exige marcar a caixa de aceite antes de liberar o botão
    "Aceitar e continuar"; tem também a opção "Recusar".
"""

import flet as ft

from utils.termos import TEXTO_TERMOS_USO, TEXTO_POLITICA_PRIVACIDADE, VERSAO_TERMOS_ATUAL


def _abrir_dialog(page: ft.Page, dialog: ft.AlertDialog):
    if dialog not in page.overlay:
        page.overlay.append(dialog)
    if hasattr(page, "open"):
        try:
            page.open(dialog)
            return
        except Exception:
            pass
    dialog.open = True
    page.update()


def _fechar_dialog(page: ft.Page, dialog: ft.AlertDialog):
    if hasattr(page, "close"):
        try:
            page.close(dialog)
            return
        except Exception:
            pass
    dialog.open = False
    page.update()


def _conteudo_documentos() -> ft.Control:
    """Abas 'Termos de Uso' e 'Política de Privacidade', com rolagem
    independente — mesmo padrão de ft.TabBar/ft.TabBarView usado em
    pages/relatorios/view.py (compatível com Flet 0.84.0)."""

    aba_termos = ft.Container(
        padding=ft.padding.only(top=10),
        content=ft.Column(
            [ft.Markdown(
                TEXTO_TERMOS_USO,
                selectable=True,
                extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
            )],
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        ),
    )

    aba_privacidade = ft.Container(
        padding=ft.padding.only(top=10),
        content=ft.Column(
            [ft.Markdown(
                TEXTO_POLITICA_PRIVACIDADE,
                selectable=True,
                extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
            )],
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        ),
    )

    tabbar = ft.TabBar(
        tabs=[ft.Tab(label="Termos de Uso"), ft.Tab(label="Política de Privacidade")],
        indicator_color=ft.Colors.BLUE,
        label_color=ft.Colors.BLUE,
        unselected_label_color=ft.Colors.GREY,
    )
    tabview = ft.TabBarView(controls=[aba_termos, aba_privacidade], expand=True)

    return ft.Container(
        width=640,
        height=440,
        content=ft.Tabs(
            content=ft.Column([tabbar, tabview], expand=True, spacing=0),
            length=2,
            selected_index=0,
            expand=True,
        ),
    )


def dialog_termos(
    page: ft.Page,
    modo: str = "leitura",
    on_aceitar=None,
    on_recusar=None,
):
    """
    Exibe os Termos de Uso e a Política de Privacidade.

    modo="leitura": apenas consulta, com botão "Fechar".
    modo="aceite": bloqueia o uso até marcar "Li e aceito..." e clicar
        em "Aceitar e continuar"; alternativa é "Recusar".

    on_aceitar / on_recusar: corrotinas (async def sem argumentos)
    chamadas via page.run_task() após o diálogo fechar.
    """

    cb_aceite = ft.Checkbox(
        label="Li e aceito os Termos de Uso e a Política de Privacidade.",
        value=False,
    )

    btn_aceitar = ft.FilledButton("Aceitar e continuar", disabled=True)
    btn_recusar = ft.TextButton("Recusar")
    btn_fechar = ft.TextButton("Fechar")

    def _on_change_checkbox(e):
        btn_aceitar.disabled = not cb_aceite.value
        try:
            btn_aceitar.update()
        except Exception:
            page.update()

    cb_aceite.on_change = _on_change_checkbox

    def _clique_aceitar(e):
        _fechar_dialog(page, dialog)
        if on_aceitar:
            page.run_task(on_aceitar)

    def _clique_recusar(e):
        _fechar_dialog(page, dialog)
        if on_recusar:
            page.run_task(on_recusar)

    btn_aceitar.on_click = _clique_aceitar
    btn_recusar.on_click = _clique_recusar
    btn_fechar.on_click = lambda e: _fechar_dialog(page, dialog)

    if modo == "aceite":
        titulo = "Antes de continuar"
        rodape = ft.Column(
            [
                ft.Text(
                    f"Versão vigente: {VERSAO_TERMOS_ATUAL}",
                    size=11, color=ft.Colors.GREY_500,
                ),
                cb_aceite,
            ],
            spacing=4, tight=True,
        )
        acoes = [btn_recusar, btn_aceitar]
    else:
        titulo = "Termos de Uso e Política de Privacidade"
        rodape = ft.Container()
        acoes = [btn_fechar]

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text(titulo, weight=ft.FontWeight.BOLD),
        content=ft.Column(
            [_conteudo_documentos(), rodape],
            tight=True, spacing=10,
        ),
        actions=acoes,
        actions_alignment=ft.MainAxisAlignment.END,
    )

    _abrir_dialog(page, dialog)