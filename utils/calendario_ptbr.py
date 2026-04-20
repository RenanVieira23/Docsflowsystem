import flet as ft
from datetime import date
import calendar


# -------------------------------------------------------------------
# Estado por Page: guarda dialog + mês/ano atuais para reutilizar
# -------------------------------------------------------------------
_PAGE_STATE: dict[int, dict] = {}


def calendario_ptbr(page: ft.Page, on_select):
    """
    Calendário pt-BR reutilizável mantendo a API original:

        calendario_ptbr(page, on_select)

    Melhorias:
      - Reutiliza o mesmo AlertDialog (não acumula no overlay)
      - Mantém mês/ano da última navegação para aquela Page
      - Mantém callback on_select(date) igual
    """
    key = id(page)

    # estado inicial por page
    if key not in _PAGE_STATE:
        hoje = date.today()
        _PAGE_STATE[key] = {
            "ano": hoje.year,
            "mes": hoje.month,
            "dialog": None,
            "grid": None,
        }

    state = _PAGE_STATE[key]

    meses = [
        "Janeiro", "Fevereiro", "Março", "Abril",
        "Maio", "Junho", "Julho", "Agosto",
        "Setembro", "Outubro", "Novembro", "Dezembro",
    ]

    dias_semana = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]

    # reutiliza grid
    grid = state.get("grid")
    if grid is None:
        grid = ft.Column(spacing=5)
        state["grid"] = grid

    # ano/mes atuais (persistentes)
    ano = state["ano"]
    mes = state["mes"]

    # =========================
    # Funções de navegação
    # =========================
    def montar_calendario():
        nonlocal ano, mes

        grid.controls.clear()

        # Cabeçalho
        grid.controls.append(
            ft.Row(
                [
                    ft.TextButton("⏪", tooltip="Ano anterior", on_click=voltar_ano),
                    ft.TextButton("◀", tooltip="Mês anterior", on_click=voltar_mes),
                    ft.Text(f"{meses[mes - 1]} / {ano}", weight=ft.FontWeight.BOLD),
                    ft.TextButton("▶", tooltip="Próximo mês", on_click=avancar_mes),
                    ft.TextButton("⏩", tooltip="Próximo ano", on_click=avancar_ano),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            )
        )

        # Dias da semana
        grid.controls.append(
            ft.Row([ft.Text(d, width=40, text_align="center") for d in dias_semana])
        )

        cal = calendar.monthcalendar(ano, mes)

        for semana in cal:
            linha = []
            for dia in semana:
                if dia == 0:
                    linha.append(ft.Text("", width=40))
                else:
                    linha.append(
                        ft.TextButton(
                            str(dia),
                            width=40,
                            on_click=lambda e, d=dia: selecionar_dia(d),
                        )
                    )
            grid.controls.append(ft.Row(linha))

        page.update()

    def selecionar_dia(dia: int):
        nonlocal ano, mes

        # persiste mês/ano antes de fechar
        state["ano"] = ano
        state["mes"] = mes

        # fecha rápido
        dialog.open = False
        page.update()

        # callback
        on_select(date(ano, mes, dia))

    def voltar_mes(e):
        nonlocal mes, ano
        mes -= 1
        if mes == 0:
            mes = 12
            ano -= 1

        state["ano"] = ano
        state["mes"] = mes
        montar_calendario()

    def avancar_mes(e):
        nonlocal mes, ano
        mes += 1
        if mes == 13:
            mes = 1
            ano += 1

        state["ano"] = ano
        state["mes"] = mes
        montar_calendario()

    def voltar_ano(e):
        nonlocal ano
        ano -= 1

        state["ano"] = ano
        montar_calendario()

    def avancar_ano(e):
        nonlocal ano
        ano += 1

        state["ano"] = ano
        montar_calendario()

    # =========================
    # Dialog (reutilizável)
    # =========================
    dialog = state.get("dialog")

    def fechar(e=None):
        # persiste mês/ano atual ao fechar
        state["ano"] = ano
        state["mes"] = mes
        dialog.open = False
        page.update()

    if dialog is None:
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Selecionar data"),
            content=grid,
            actions=[ft.TextButton("Cancelar", on_click=fechar)],
        )
        state["dialog"] = dialog

        if dialog not in page.overlay:
            page.overlay.append(dialog)
    else:
        # garante que o dialog atualize o conteúdo/ação se precisar
        dialog.content = grid
        dialog.actions = [ft.TextButton("Cancelar", on_click=fechar)]

        if dialog not in page.overlay:
            page.overlay.append(dialog)

    # monta e abre
    montar_calendario()
    dialog.open = True
    page.update()