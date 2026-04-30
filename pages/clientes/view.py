import flet as ft
import asyncio

from database.models import get_clientes
from pages.clientes.form import novo_cliente_dialog, editar_cliente_dialog
from utils.table_sort import SortState


# ======================================================
# VIEW
# ======================================================

class ClientesView(ft.Column):

    def __init__(self, page: ft.Page):
        super().__init__(expand=True, spacing=10)

        self.app_page = page

        self.page_size = 10
        self.current_page = 1
        self.clientes = []

        # Ordenação
        self.sort = SortState(default_col=0)
        self.sort.set_callback(self.atualizar_tabela)

        # Chaves por índice de coluna (None = não ordenável)
        self.sort_chaves = ["id", "nome", "tipo", "documento", "sigla", None]

        # =========================
        # LOADING
        # =========================
        self.loading = ft.ProgressRing(visible=False, width=22, height=22, stroke_width=2)

        # =========================
        # TABELA
        # =========================
        self.tabela = ft.DataTable(
            column_spacing=14,
            heading_row_height=38,
            data_row_min_height=36,
            divider_thickness=0.5,
            sort_column_index=self.sort.col,
            sort_ascending=self.sort.asc,
            columns=[
                ft.DataColumn(ft.Text("ID"),        on_sort=self.sort.handler(0)),
                ft.DataColumn(ft.Text("Nome"),      on_sort=self.sort.handler(1)),
                ft.DataColumn(ft.Text("Tipo"),      on_sort=self.sort.handler(2)),
                ft.DataColumn(ft.Text("Documento"), on_sort=self.sort.handler(3)),
                ft.DataColumn(ft.Text("Sigla"),     on_sort=self.sort.handler(4)),
                ft.DataColumn(ft.Text("Ações")),
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
                    ft.Text("Clientes", size=22, weight=ft.FontWeight.BOLD),
                    ft.Row(
                        [
                            ft.FilledButton("Novo cliente", height=38, on_click=self.abrir_dialog),
                            ft.OutlinedButton("Atualizar", height=38, on_click=self.recarregar),
                            self.loading,
                        ],
                        spacing=8,
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),

            ft.Divider(height=1),

            ft.Container(
                height=500,
                content=ft.Column([self.tabela], scroll=ft.ScrollMode.AUTO),
            ),

            ft.Row(
                [
                    ft.TextButton("Anterior", on_click=self.anterior),
                    self.lbl_pagina,
                    ft.TextButton("Próxima", on_click=self.proxima),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=16,
            ),
        ])

        self.app_page.run_task(self._carregar_dados)


    # ======================================================
    # CARREGAMENTO
    # ======================================================

    async def _carregar_dados(self):
        self.loading.visible = True
        self.app_page.update()

        try:
            tenant_id = self.app_page.local_store.get("tenant_id")
            dados = await asyncio.to_thread(get_clientes, tenant_id, True)
        except Exception as ex:
            print("Erro clientes:", ex)
            dados = []

        self.clientes = dados or []
        self.current_page = 1
        self.loading.visible = False
        self.atualizar_tabela()

    def recarregar(self, e=None):
        self.app_page.run_task(self._carregar_dados)


    # ======================================================
    # TABELA
    # ======================================================

    def atualizar_tabela(self):
        self.tabela.rows.clear()

        # Ordena
        lista = self.sort.apply(self.clientes, self.sort_chaves)

        total = len(lista)
        total_pages = max(1, (total + self.page_size - 1) // self.page_size)

        ini = (self.current_page - 1) * self.page_size
        fim = ini + self.page_size

        for c in lista[ini:fim]:
            botoes = [
                ft.TextButton("Ver",    on_click=lambda e, cc=c: self.ver(cc)),
                ft.TextButton("Editar", on_click=lambda e, cc=c: self.editar(cc)),
            ]

            self.tabela.rows.append(
                ft.DataRow(cells=[
                    ft.DataCell(ft.Text(str(c.get("id", "")))),
                    ft.DataCell(ft.Text(c.get("nome", ""))),
                    ft.DataCell(ft.Text(c.get("tipo", ""))),
                    ft.DataCell(ft.Text(c.get("documento", ""))),
                    ft.DataCell(ft.Text(c.get("sigla") or "-")),
                    ft.DataCell(ft.Row(botoes, spacing=6)),
                ])
            )

        # Atualiza estado de ordenação no DataTable
        self.tabela.sort_column_index = self.sort.col
        self.tabela.sort_ascending    = self.sort.asc

        self.lbl_pagina.value = f"Página {self.current_page} / {total_pages}"
        self.tabela.update()
        self.lbl_pagina.update()


    # ======================================================
    # PAGINAÇÃO
    # ======================================================

    def proxima(self, e):
        total = len(self.clientes)
        if self.current_page * self.page_size < total:
            self.current_page += 1
            self.atualizar_tabela()

    def anterior(self, e):
        if self.current_page > 1:
            self.current_page -= 1
            self.atualizar_tabela()


    # ======================================================
    # CRUD
    # ======================================================

    def abrir_dialog(self, e):
        dialog = novo_cliente_dialog(self.app_page, self.recarregar)
        if dialog not in self.app_page.overlay:
            self.app_page.overlay.append(dialog)
        dialog.open = True
        self.app_page.update()

    def editar(self, cliente):
        dialog = editar_cliente_dialog(self.app_page, cliente, self.recarregar)
        if dialog not in self.app_page.overlay:
            self.app_page.overlay.append(dialog)
        dialog.open = True
        self.app_page.update()

    def ver(self, cliente):
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Cliente"),
            content=ft.Column(
                [
                    ft.Text(f"Nome: {cliente.get('nome')}"),
                    ft.Text(f"Tipo: {cliente.get('tipo')}"),
                    ft.Text(f"Documento: {cliente.get('documento')}"),
                    ft.Text(f"Sigla: {cliente.get('sigla')}"),
                ],
                spacing=8,
            ),
            actions=[
                ft.TextButton("Fechar", on_click=lambda e: self.fechar(dialog))
            ],
        )
        self.app_page.overlay.append(dialog)
        dialog.open = True
        self.app_page.update()

    def fechar(self, dialog):
        dialog.open = False
        self.app_page.update()


# ======================================================
# EXPORT
# ======================================================

def clientes_view(page: ft.Page):
    return ClientesView(page)