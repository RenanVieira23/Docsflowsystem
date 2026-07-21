import flet as ft
import asyncio

from database.models import get_partes
from database.supabase_client import run_db
from pages.partes.form import nova_parte_dialog, editar_parte_dialog
from utils.permissoes import pode


# ======================================================
# VIEW
# ======================================================

class PartesView(ft.Column):

    def __init__(self, page: ft.Page):
        super().__init__(expand=True, spacing=10)

        self.app_page = page
        self.tenant_id = page.local_store.get("tenant_id") if hasattr(page, "local_store") else None
        self.page_size = 10
        self.current_page = 1
        self.partes = []

        # =========================
        # LOADING
        # =========================
        self.loading = ft.ProgressRing(
            visible=False, width=22, height=22, stroke_width=2
        )

        # =========================
        # BUSCA
        # =========================
        self.busca = ft.TextField(
            hint_text="Buscar por nome ou documento...",
            width=320,
        )
        self.busca.on_change = self.filtrar

        # =========================
        # TABELA
        # =========================
        self.tabela = ft.DataTable(
            column_spacing=14,
            heading_row_height=38,
            data_row_min_height=36,
            divider_thickness=0.5,
            columns=[
                ft.DataColumn(ft.Text("ID")),
                ft.DataColumn(ft.Text("Nome")),
                ft.DataColumn(ft.Text("Tipo")),
                ft.DataColumn(ft.Text("Documento")),
                ft.DataColumn(ft.Text("Ações")),
            ],
            rows=[],
        )

        self.lbl_pagina = ft.Text()
        self._partes_filtradas = []

        # =========================
        # LAYOUT
        # =========================
        self.controls.extend([

            ft.Row(
                [
                    ft.Text("Partes", size=22, weight=ft.FontWeight.BOLD),
                    ft.Row(
                        [
                            ft.FilledButton(
                                "Nova Parte",
                                height=38,
                                on_click=self.abrir_dialog,
                                visible=pode(page, "partes", "cadastrar"),
                            ),
                            ft.OutlinedButton(
                                "Atualizar",
                                height=38,
                                on_click=self.recarregar,
                            ),
                            self.loading,
                        ],
                        spacing=8,
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),

            ft.Row([self.busca], spacing=8),

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
            dados = await run_db(self.app_page, get_partes, self.tenant_id)
        except Exception as ex:
            print("Erro partes:", ex)
            dados = []

        self.partes = dados or []
        self.current_page = 1
        self.loading.visible = False
        self._aplicar_filtro()


    def recarregar(self, e=None):
        self.app_page.run_task(self._carregar_dados)


    # ======================================================
    # FILTRO
    # ======================================================

    def filtrar(self, e):
        self.current_page = 1
        self._aplicar_filtro()


    def _aplicar_filtro(self):

        termo = (self.busca.value or "").lower().strip()

        if termo:
            self._partes_filtradas = [
                p for p in self.partes
                if termo in (p.get("nome") or "").lower()
                or termo in (p.get("documento") or "").lower()
            ]
        else:
            self._partes_filtradas = list(self.partes)

        self.atualizar_tabela()


    # ======================================================
    # TABELA
    # ======================================================

    def atualizar_tabela(self):

        self.tabela.rows.clear()

        total = len(self._partes_filtradas)
        total_pages = max(1, (total + self.page_size - 1) // self.page_size)

        ini = (self.current_page - 1) * self.page_size
        fim = ini + self.page_size

        for p in self._partes_filtradas[ini:fim]:

            self.tabela.rows.append(
                ft.DataRow(cells=[
                    ft.DataCell(ft.Text(str(p.get("id", "")))),
                    ft.DataCell(ft.Text(p.get("nome", ""))),
                    ft.DataCell(ft.Text(p.get("tipo", ""))),
                    ft.DataCell(ft.Text(p.get("documento", ""))),
                    ft.DataCell(
                        ft.Row([
                            ft.TextButton(
                                "Editar",
                                on_click=lambda e, pp=p: self.editar(pp),
                                visible=pode(self.app_page, "partes", "editar"),
                            ),
                        ], spacing=6)
                    ),
                ])
            )

        self.lbl_pagina.value = f"Página {self.current_page} / {total_pages}"
        self.tabela.update()
        self.lbl_pagina.update()


    # ======================================================
    # PAGINAÇÃO
    # ======================================================

    def proxima(self, e):
        if self.current_page * self.page_size < len(self._partes_filtradas):
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
        dialog = nova_parte_dialog(self.app_page, self.recarregar)
        if dialog not in self.app_page.overlay:
            self.app_page.overlay.append(dialog)
        dialog.open = True
        self.app_page.update()


    def editar(self, parte):
        dialog = editar_parte_dialog(self.app_page, parte, self.recarregar)
        if dialog not in self.app_page.overlay:
            self.app_page.overlay.append(dialog)
        dialog.open = True
        self.app_page.update()


# ======================================================
# EXPORT
# ======================================================

def partes_view(page: ft.Page):
    return PartesView(page)