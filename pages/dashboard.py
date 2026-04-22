import flet as ft
import asyncio
from database.models import (
    get_clientes,
    get_contratos,
    get_total_prazos,
    get_total_alertas_enviados,
    get_alertas_por_periodo,
)


def dashboard_view(page: ft.Page):

    page.title = "Dashboard"

    def card(titulo, valor, cor):
        return ft.Container(
            expand=True,
            padding=20,
            border_radius=14,
            bgcolor=cor,
            border=ft.border.all(1, ft.Colors.GREY_200),
            content=ft.Column(
                [
                    ft.Text(titulo, size=13, color=ft.Colors.GREY_600),
                    ft.Text(str(valor), size=32, weight=ft.FontWeight.BOLD, color=ft.Colors.GREY_900),
                ],
                spacing=4,
            ),
        )

    cards_row = ft.Row(
        [
            card("Clientes",        "...", ft.Colors.BLUE_50),
            card("Contratos",       "...", ft.Colors.GREEN_50),
            card("Alertas enviados","...", ft.Colors.AMBER_50),
            card("Alertas pendentes","...",ft.Colors.RED_50),
        ],
        spacing=16,
    )

    grafico_container = ft.Container(
        padding=20,
        border_radius=12,
        bgcolor=ft.Colors.WHITE,
        border=ft.border.all(1, ft.Colors.GREY_200),
        content=ft.Column(
            [
                ft.Text("Alertas próximos (próximos 30 dias)", size=15, weight=ft.FontWeight.W_600),
                ft.Container(
                    content=ft.Text("Carregando...", color=ft.Colors.GREY_400, italic=True, size=13),
                    padding=ft.padding.symmetric(vertical=20),
                ),
            ],
            spacing=12,
        ),
    )

    loading  = ft.ProgressRing(visible=False, width=20, height=20, stroke_width=2)
    btn_refresh = ft.OutlinedButton(
        "Atualizar", height=34, icon=ft.Icons.REFRESH,
        on_click=lambda e: page.run_task(carregar),
    )

    async def carregar():
        loading.visible = True
        page.update()

        # ── tenant isolado ──────────────────────────────────
        tenant_id = page.local_store.get("tenant_id") if hasattr(page, "local_store") else None

        try:
            clientes   = await asyncio.to_thread(get_clientes,  tenant_id) or []
            contratos  = await asyncio.to_thread(get_contratos, tenant_id) or []
            tot_prazos = await asyncio.to_thread(get_total_prazos) or 0
            enviados   = await asyncio.to_thread(get_total_alertas_enviados) or 0
            alertas    = await asyncio.to_thread(get_alertas_por_periodo, 30) or []
        except Exception as ex:
            print("Erro dashboard:", ex)
            clientes = contratos = alertas = []
            tot_prazos = enviados = 0

        pendentes = max(0, tot_prazos - enviados)

        vals    = [len(clientes), len(contratos), enviados, pendentes]
        cores   = [ft.Colors.BLUE_50, ft.Colors.GREEN_50, ft.Colors.AMBER_50, ft.Colors.RED_50]
        titulos = ["Clientes", "Contratos", "Alertas enviados", "Alertas pendentes"]
        for i, c in enumerate(cards_row.controls):
            c.content.controls[0].value = titulos[i]
            c.content.controls[1].value = str(vals[i])
            c.bgcolor = cores[i]

        urgente = [a for a in alertas if a["dias"] <= 7]
        medio   = [a for a in alertas if 7 < a["dias"] <= 15]
        normal  = [a for a in alertas if a["dias"] > 15]

        def _barra(label, qtd, cor, total):
            pct = (qtd / total * 100) if total > 0 else 0
            return ft.Column(
                [
                    ft.Row(
                        [
                            ft.Container(width=max(4, pct * 3.5), height=28, border_radius=6, bgcolor=cor),
                            ft.Text(f"{qtd}", size=13, weight=ft.FontWeight.W_500),
                        ],
                        spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Text(label, size=12, color=ft.Colors.GREY_600),
                ],
                spacing=2,
            )

        total_alertas = len(alertas)
        if total_alertas == 0:
            grafico_content = ft.Text(
                "Nenhum prazo nos próximos 30 dias.",
                color=ft.Colors.GREY_400, italic=True, size=13,
            )
        else:
            grafico_content = ft.Column(
                [
                    _barra("Urgente (≤ 7 dias)",  len(urgente), ft.Colors.RED_400,    total_alertas),
                    _barra("Médio (8–15 dias)",    len(medio),   ft.Colors.ORANGE_400, total_alertas),
                    _barra("Normal (> 15 dias)",   len(normal),  ft.Colors.GREEN_400,  total_alertas),
                ],
                spacing=12,
            )

        grafico_container.content = ft.Column(
            [
                ft.Text(
                    f"Alertas próximos — {total_alertas} prazos nos próximos 30 dias",
                    size=14, weight=ft.FontWeight.W_600,
                ),
                grafico_content,
            ],
            spacing=12,
        )

        loading.visible = False
        page.update()

    page.run_task(carregar)

    return ft.Container(
        padding=24,
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Column(
                            [
                                ft.Text("Dashboard", size=26, weight=ft.FontWeight.BOLD),
                                ft.Text("Visão geral do sistema", color=ft.Colors.GREY_600, size=13),
                            ],
                            spacing=2,
                        ),
                        ft.Row([loading, btn_refresh], spacing=8),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Container(height=12),
                cards_row,
                ft.Container(height=20),
                grafico_container,
            ],
            spacing=0,
            expand=True,
        ),
    )