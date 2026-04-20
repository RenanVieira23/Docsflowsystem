import flet as ft
import asyncio

from database.models import get_alertas_por_periodo
from utils.dataptbr import data_db_para_br
from utils.table_sort import SortState


# ======================================================
# VIEW
# ======================================================

class PainelAlertasView(ft.Column):

    def __init__(self, page: ft.Page):
        super().__init__(expand=True, spacing=12)

        self.app_page = page
        self.dias  = 7
        self.dados = []

        # Ordenação — colunas: Cliente, Apelido, Observação, Vencimento, Dias, Status
        self.sort = SortState(default_col=4, default_asc=True)  # padrão: dias asc
        self.sort.set_callback(self.atualizar_tabela)
        self.sort_chaves = ["cliente", "contrato", "observacao", "vencimento", "dias", "status"]

        # =========================
        # LOADING
        # =========================
        self.loading = ft.ProgressRing(visible=False, width=22, height=22, stroke_width=2)

        # =========================
        # FILTRO
        # =========================
        self.dd_dias = ft.Dropdown(
            width=160, value="7",
            options=[
                ft.dropdown.Option("7"),
                ft.dropdown.Option("15"),
                ft.dropdown.Option("30"),
                ft.dropdown.Option("60"),
                ft.dropdown.Option("90"),
            ],
        )

        self.btn_buscar = ft.FilledButton("Buscar", on_click=self.buscar)

        # =========================
        # TABELA
        # =========================
        self.tabela = ft.DataTable(
            column_spacing=14,
            heading_row_height=38,
            divider_thickness=0.5,
            sort_column_index=self.sort.col,
            sort_ascending=self.sort.asc,
            columns=[
                ft.DataColumn(ft.Text("Cliente"),    on_sort=self.sort.handler(0)),
                ft.DataColumn(ft.Text("Apelido"),    on_sort=self.sort.handler(1)),
                ft.DataColumn(ft.Text("Observação"), on_sort=self.sort.handler(2)),
                ft.DataColumn(ft.Text("Vencimento"), on_sort=self.sort.handler(3)),
                ft.DataColumn(ft.Text("Dias"),       on_sort=self.sort.handler(4), numeric=True),
                ft.DataColumn(ft.Text("Status"),     on_sort=self.sort.handler(5)),
            ],
            rows=[],
        )

        # =========================
        # LAYOUT
        # =========================
        self.controls.extend([
            ft.Row(
                [
                    ft.Text("Painel de Alertas", size=22, weight=ft.FontWeight.BOLD),
                    ft.Row(
                        [
                            ft.Text("Período:"),
                            self.dd_dias,
                            self.btn_buscar,
                            self.loading,
                        ],
                        spacing=8,
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),

            ft.Divider(),

            ft.Container(
                expand=True,
                content=ft.Column([self.tabela], scroll=ft.ScrollMode.AUTO),
            ),
        ])

        self.app_page.run_task(self._carregar)

    # ======================================================
    # DADOS
    # ======================================================

    async def _carregar(self):
        self.loading.visible = True
        self.update()

        try:
            dados = await asyncio.to_thread(get_alertas_por_periodo, self.dias)
        except Exception as ex:
            print("Erro painel alertas:", ex)
            dados = []

        self.dados = dados or []
        self.loading.visible = False
        self.atualizar_tabela()

    def buscar(self, e):
        self.dias = int(self.dd_dias.value)
        self.app_page.run_task(self._carregar)

    # ======================================================
    # TABELA
    # ======================================================

    def atualizar_tabela(self):
        self.tabela.rows.clear()

        lista = self.sort.apply(self.dados, self.sort_chaves)

        for d in lista:
            if d["dias"] <= 7:
                cor = ft.Colors.RED
            elif d["dias"] <= 15:
                cor = ft.Colors.ORANGE
            else:
                cor = ft.Colors.GREEN

            self.tabela.rows.append(
                ft.DataRow(cells=[
                    ft.DataCell(ft.Text(d["cliente"])),
                    ft.DataCell(ft.Text(d["contrato"])),
                    ft.DataCell(ft.Text(d["observacao"] or "")),
                    ft.DataCell(ft.Text(data_db_para_br(d["vencimento"]))),
                    ft.DataCell(ft.Text(f"{d['dias']} dias", color=cor, weight=ft.FontWeight.BOLD)),
                    ft.DataCell(ft.Text(
                        d["status"],
                        color=ft.Colors.GREEN if d["status"] == "Enviado" else ft.Colors.RED,
                    )),
                ])
            )

        self.tabela.sort_column_index = self.sort.col
        self.tabela.sort_ascending    = self.sort.asc
        self.tabela.update()


# ======================================================
# EXPORT
# ======================================================

def painel_view(page: ft.Page):
    return PainelAlertasView(page)