import flet as ft
from database.models import (
    get_clientes,
    get_contratos,
    get_total_prazos,
    get_total_alertas_enviados,
    get_alertas_por_periodo,
)


def dashboard_view(page: ft.Page):

    page.title = "Dashboard"

    # =========================
    # DADOS
    # =========================

    clientes = get_clientes() or []
    contratos = get_contratos() or []

    total_clientes = len(clientes)
    total_contratos = len(contratos)

    # ALERTAS
    total_prazos = get_total_prazos() or 0
    alertas_enviados = get_total_alertas_enviados() or 0
    alertas_pendentes = max(0, total_prazos - alertas_enviados)


    # =========================
    # CARD PADRÃO
    # =========================

    def card(titulo, valor, cor):

        return ft.Container(
            expand=True,
            padding=20,
            border_radius=14,
            bgcolor=cor,
            border=ft.border.all(1, ft.Colors.GREY_200),
            content=ft.Column(
                [
                    ft.Text(
                        titulo,
                        size=14,
                        color=ft.Colors.GREY_700,
                    ),

                    ft.Text(
                        str(valor),
                        size=34,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.GREY_900,
                    ),
                ],
                spacing=6,
            ),
        )


    # =========================
    # CARDS RESUMO
    # =========================

    cards_resumo = ft.Row(
        [
            card("Clientes", total_clientes, ft.Colors.BLUE_50),
            card("Contratos", total_contratos, ft.Colors.GREEN_50),
            card("Alertas enviados", alertas_enviados, ft.Colors.AMBER_50),
            card("Alertas pendentes", alertas_pendentes, ft.Colors.RED_50),
        ],
        spacing=16,
    )


    # =========================
    # LAYOUT FINAL
    # =========================

    return ft.Container(
        padding=24,
        content=ft.Column(
            [
                # TÍTULO
                ft.Text(
                    "Dashboard",
                    size=26,
                    weight=ft.FontWeight.BOLD,
                ),

                ft.Text(
                    "Visão geral do sistema",
                    color=ft.Colors.GREY_600,
                ),

                ft.Container(height=10),

                # CARDS
                cards_resumo,

                ft.Container(height=20),

               
            ],
            spacing=12,
            expand=True,
        ),
    )

    def criar_grafico_alertas(self):

        dados = get_alertas_por_periodo()

        bars = []

        for d in dados:

            bars.append(
               ft.BarChartGroup(
                        x=str(d["dias"]),
                    bar_rods=[
                        ft.BarChartRod(
                            from_y=0,
                            to_y=d["total"],
                            width=22,
                            color=ft.Colors.BLUE,
                            tooltip=f"{d['total']} alertas"
                        )
                    ]
                )
            )

        grafico = ft.BarChart(
            bar_groups=bars,
            border=ft.Border(
                left=ft.BorderSide(1),
                bottom=ft.BorderSide(1),
            ),
            left_axis=ft.ChartAxis(
                labels_size=40,
            ),
            bottom_axis=ft.ChartAxis(
                labels_size=40,
            ),
            horizontal_grid_lines=ft.ChartGridLines(
                interval=5,
                width=1,
                color=ft.Colors.GREY_300,
            ),
            max_y=max([d["total"] for d in dados] + [5]),
            expand=True,
        )

        return ft.Container(
            padding=20,
            border_radius=12,
            bgcolor=ft.Colors.WHITE,
            content=ft.Column(
                [
                    ft.Text(
                        "📊 Alertas por período",
                        size=18,
                        weight=ft.FontWeight.BOLD,
                    ),
                    grafico,
                ],
                spacing=15,
            ),
        )

