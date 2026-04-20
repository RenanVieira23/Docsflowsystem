import flet as ft
import asyncio
import pandas as pd
from datetime import datetime
import os, sys, subprocess, io

from database.models import get_relatorio_notificacoes_export
from utils.dataptbr import data_db_para_br
from utils.table_sort import SortState


# ======================================================
# VIEW
# ======================================================

class RelatoriosView(ft.Column):

    def __init__(self, page: ft.Page):
        super().__init__(expand=True, spacing=12)

        self.app_page = page

        self.page_size    = 10
        self.current_page = 1
        self.status       = "todos"
        self.todos_dados  = []
        self.dados_pagina = []

        # Ordenação — Cliente, Apelido, Observação, Início, Vencimento, Dias antes, Status
        self.sort = SortState(default_col=0)
        self.sort.set_callback(self._render_tabela)
        self.sort_chaves = ["cliente", "contrato", "observacao", "inicio", "vencimento", "dias_antes", "status"]

        # =========================
        # LOADING
        # =========================
        self.loading = ft.ProgressRing(visible=False, width=22, height=22, stroke_width=2)

        # =========================
        # FILTRO
        # =========================
        self.dd_status = ft.Dropdown(
            width=180, value="todos",
            options=[
                ft.dropdown.Option("todos",    "Todos"),
                ft.dropdown.Option("enviados", "Enviados"),
                ft.dropdown.Option("pendentes","Pendentes"),
            ],
        )

        self.btn_filtrar  = ft.FilledButton("Filtrar",        on_click=self.aplicar_filtro)
        self.btn_exportar = ft.OutlinedButton("Exportar Excel", icon=ft.Icons.DOWNLOAD, on_click=self.exportar_excel)

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
                ft.DataColumn(ft.Text("Início"),     on_sort=self.sort.handler(3)),
                ft.DataColumn(ft.Text("Vencimento"), on_sort=self.sort.handler(4)),
                ft.DataColumn(ft.Text("Dias antes"), on_sort=self.sort.handler(5), numeric=True),
                ft.DataColumn(ft.Text("Status"),     on_sort=self.sort.handler(6)),
            ],
            rows=[],
        )

        self.lbl_pagina = ft.Text()

        # =========================
        # LAYOUT
        # =========================
        self.controls.extend([
            ft.Row(
                [
                    ft.Text("Relatório de Alertas", size=22, weight=ft.FontWeight.BOLD),
                    ft.Row(
                        [self.dd_status, self.btn_filtrar, self.btn_exportar, self.loading],
                        spacing=8,
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),

            ft.Divider(),

            ft.Container(
                height=520,
                content=ft.Column([self.tabela], scroll=ft.ScrollMode.AUTO),
            ),

            ft.Row(
                [
                    ft.OutlinedButton("◀ Anterior", on_click=self.anterior),
                    self.lbl_pagina,
                    ft.OutlinedButton("Próxima ▶",  on_click=self.proxima),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=12,
            ),
        ])

        self.app_page.run_task(self._carregar_tudo)

    # ======================================================
    # DADOS
    # ======================================================

    async def _carregar_tudo(self):
        self.loading.visible = True
        self.update()

        try:
            dados = await asyncio.to_thread(get_relatorio_notificacoes_export, self.status)
        except Exception as ex:
            print("Erro relatório:", ex)
            dados = []

        self.todos_dados  = dados or []
        self.current_page = 1
        self.loading.visible = False
        self._render_tabela()

    def aplicar_filtro(self, e):
        self.status = self.dd_status.value
        self.app_page.run_task(self._carregar_tudo)

    # ======================================================
    # TABELA
    # ======================================================

    def _render_tabela(self):
        self.tabela.rows.clear()

        lista = self.sort.apply(self.todos_dados, self.sort_chaves)

        total       = len(lista)
        total_pages = max(1, (total + self.page_size - 1) // self.page_size)

        ini = (self.current_page - 1) * self.page_size
        fim = ini + self.page_size

        for d in lista[ini:fim]:
            cor = ft.Colors.GREEN if d["status"] == "Enviado" else ft.Colors.RED

            self.tabela.rows.append(
                ft.DataRow(cells=[
                    ft.DataCell(ft.Text(d["cliente"])),
                    ft.DataCell(ft.Text(d["contrato"])),
                    ft.DataCell(ft.Text(d["observacao"])),
                    ft.DataCell(ft.Text(data_db_para_br(d["inicio"]))),
                    ft.DataCell(ft.Text(data_db_para_br(d["vencimento"]))),
                    ft.DataCell(ft.Text(str(d["dias_antes"]))),
                    ft.DataCell(ft.Text(d["status"], color=cor, weight=ft.FontWeight.BOLD)),
                ])
            )

        self.tabela.sort_column_index = self.sort.col
        self.tabela.sort_ascending    = self.sort.asc
        self.lbl_pagina.value = f"Página {self.current_page} / {total_pages}"
        self.tabela.update()
        self.lbl_pagina.update()

    # ======================================================
    # PAGINAÇÃO
    # ======================================================

    def proxima(self, e):
        if self.current_page * self.page_size < len(self.todos_dados):
            self.current_page += 1
            self._render_tabela()

    def anterior(self, e):
        if self.current_page > 1:
            self.current_page -= 1
            self._render_tabela()

    # ======================================================
    # FEEDBACK / EXPORTAÇÃO
    # ======================================================

    def _snack(self, msg):
        self.app_page.snack_bar = ft.SnackBar(ft.Text(msg))
        self.app_page.snack_bar.open = True
        self.app_page.update()

    async def _exportar_async(self):
        if not self.todos_dados:
            self._snack("Nenhum dado para exportar.")
            return

        self.loading.visible = True
        self.update()

        try:
            df = await asyncio.to_thread(pd.DataFrame, self.todos_dados)
            df["inicio"]     = df["inicio"].apply(data_db_para_br)
            df["vencimento"] = df["vencimento"].apply(data_db_para_br)

            nome   = f"relatorio_alertas_{self.status}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            buffer = io.BytesIO()
            await asyncio.to_thread(df.to_excel, buffer, index=False,
                sheet_name="Relatório de Alertas", engine="openpyxl")
            buffer.seek(0)
        except Exception as ex:
            print("Erro exportar:", ex)
            self.loading.visible = False
            self.update()
            self._snack("Erro ao gerar arquivo.")
            return

        self.loading.visible = False
        self.update()

        try:
            if self.app_page.web:
                self.app_page.download(buffer.getvalue(), file_name=nome)
                self._snack("Download iniciado.")
                return
        except:
            pass

        try:
            pasta   = os.path.join(os.path.expanduser("~"), "Downloads")
            os.makedirs(pasta, exist_ok=True)
            caminho = os.path.join(pasta, nome)
            with open(caminho, "wb") as f:
                f.write(buffer.read())
            try:
                if sys.platform == "win32":   os.startfile(pasta)
                elif sys.platform == "darwin": subprocess.Popen(["open", pasta])
                else:                          subprocess.Popen(["xdg-open", pasta])
            except:
                pass
            self._snack("Arquivo salvo na pasta Downloads.")
        except Exception as ex:
            print("Erro salvar:", ex)
            self._snack("Erro ao exportar arquivo.")

    def exportar_excel(self, e):
        self.app_page.run_task(self._exportar_async)


# ======================================================
# EXPORT
# ======================================================

def relatorios_view(page: ft.Page):
    return RelatoriosView(page)