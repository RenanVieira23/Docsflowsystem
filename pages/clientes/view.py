import flet as ft
import asyncio

from database.models import get_clientes, update_cliente
from database.supabase_client import run_db
from pages.clientes.form import novo_cliente_dialog, editar_cliente_dialog
from utils.table_sort import SortState
from utils.permissoes import pode
from utils.erros_ui import snack_erro, snack_sucesso, banner_erro_carregamento
from utils.log_acao import log_acao


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
        self.clientes_filtrados = []
        self.status_value = "ativos"
        self._erro_carregamento = False

        # Ordenação
        self.sort = SortState(default_col=0)
        self.sort.set_callback(self.atualizar_tabela)

        # Chaves por índice de coluna (None = não ordenável)
        self.sort_chaves = ["id", "nome", "tipo", "documento", "sigla", "ativo", None]

        # =========================
        # LOADING
        # =========================
        self.loading = ft.ProgressRing(visible=False, width=22, height=22, stroke_width=2)

        # =========================
        # ÁREA DE ERRO DE CARREGAMENTO
        # =========================
        self.area_erro = ft.Container(visible=False)

        # =========================
        # STATUS (mesmo padrão de pages/contratos/view.py)
        # =========================
        self.status_seg = ft.Row(spacing=0)
        self._render_status_segment()

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
                ft.DataColumn(ft.Text("Status"),    on_sort=self.sort.handler(5)),
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
                            ft.FilledButton(
                                "Novo cliente", height=38, on_click=self.abrir_dialog,
                                visible=pode(page, "clientes", "cadastrar"),
                            ),
                            ft.OutlinedButton("Atualizar", height=38, on_click=self.recarregar),
                            self.loading,
                        ],
                        spacing=8,
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),

            ft.Row(
                [ft.Text("Status:", size=12, color=ft.Colors.GREY_700), self.status_seg],
                spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),

            ft.Divider(height=1),

            self.area_erro,

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
    # STATUS UI (mesmo padrão de pages/contratos/view.py)
    # ======================================================

    def _set_status(self, val: str):
        self.status_value = val
        self._render_status_segment()
        self._aplicar_filtro_status()
        self.app_page.update()

    def _seg_btn(self, label, value, pos):
        selected = self.status_value == value
        if pos == "left":
            radius = ft.border_radius.only(top_left=999, bottom_left=999)
        elif pos == "right":
            radius = ft.border_radius.only(top_right=999, bottom_right=999)
        else:
            radius = ft.border_radius.all(0)
        bg = ft.Colors.PRIMARY if selected else ft.Colors.WHITE
        fg = ft.Colors.WHITE if selected else ft.Colors.BLACK87
        return ft.Container(
            height=32, border=ft.border.all(1, ft.Colors.BLACK26),
            border_radius=radius, bgcolor=bg,
            padding=ft.padding.symmetric(horizontal=14),
            content=ft.Row(
                [ft.Text(label, size=12, weight=ft.FontWeight.W_600, color=fg)],
                alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            on_click=lambda e: self._set_status(value),
        )

    def _render_status_segment(self):
        self.status_seg.controls = [
            self._seg_btn("Ativos", "ativos", "left"),
            self._seg_btn("Inativos", "inativos", "mid"),
            self._seg_btn("Todos", "todos", "right"),
        ]

    def is_ativo(self, cliente: dict) -> bool:
        v = cliente.get("ativo")
        if isinstance(v, bool): return v
        if isinstance(v, str):  return v.lower() in ("true", "t", "1", "yes")
        if isinstance(v, int):  return v == 1
        return True  # cadastros antigos sem o campo — tratados como ativos

    # ======================================================
    # CARREGAMENTO
    # ======================================================

    async def _carregar_dados(self):
        self.loading.visible = True
        self._erro_carregamento = False
        self.app_page.update()

        try:
            tenant_id = self.app_page.local_store.get("tenant_id")
            dados = await run_db(self.app_page, get_clientes, tenant_id, True)
        except Exception as ex:
            print("Erro clientes:", ex)
            dados = []
            self._erro_carregamento = True

        self.clientes = dados or []
        self.current_page = 1
        self.loading.visible = False

        self.area_erro.visible = self._erro_carregamento
        if self._erro_carregamento:
            self.area_erro.content = banner_erro_carregamento("os clientes", on_retry=self.recarregar)

        self._aplicar_filtro_status()

    def recarregar(self, e=None):
        self.app_page.run_task(self._carregar_dados)

    def _aplicar_filtro_status(self):
        if self.status_value == "ativos":
            self.clientes_filtrados = [c for c in self.clientes if self.is_ativo(c)]
        elif self.status_value == "inativos":
            self.clientes_filtrados = [c for c in self.clientes if not self.is_ativo(c)]
        else:
            self.clientes_filtrados = list(self.clientes)

        self.current_page = 1
        self.atualizar_tabela()

    # ======================================================
    # TABELA
    # ======================================================

    def atualizar_tabela(self):
        self.tabela.rows.clear()

        # Ordena
        lista = self.sort.apply(self.clientes_filtrados, self.sort_chaves)

        total = len(lista)
        total_pages = max(1, (total + self.page_size - 1) // self.page_size)

        ini = (self.current_page - 1) * self.page_size
        fim = ini + self.page_size

        pode_editar = pode(self.app_page, "clientes", "editar")
        pode_excluir = pode(self.app_page, "clientes", "excluir")

        for c in lista[ini:fim]:
            ativo = self.is_ativo(c)

            botoes = [
                ft.TextButton("Ver", on_click=lambda e, cc=c: self.ver(cc)),
            ]
            if pode_editar:
                botoes.append(
                    ft.TextButton("Editar", on_click=lambda e, cc=c: self.editar(cc))
                )
            if pode_excluir:
                if ativo:
                    botoes.append(ft.TextButton(
                        "Excluir",
                        style=ft.ButtonStyle(color=ft.Colors.RED),
                        on_click=lambda e, cc=c: self.confirmar_excluir(cc),
                    ))
                else:
                    botoes.append(ft.TextButton(
                        "Reativar",
                        style=ft.ButtonStyle(color=ft.Colors.GREEN),
                        on_click=lambda e, cc=c: self.reativar(cc),
                    ))

            self.tabela.rows.append(
                ft.DataRow(cells=[
                    ft.DataCell(ft.Text(str(c.get("id", "")))),
                    ft.DataCell(ft.Text(c.get("nome", ""))),
                    ft.DataCell(ft.Text(c.get("tipo", ""))),
                    ft.DataCell(ft.Text(c.get("documento", ""))),
                    ft.DataCell(ft.Text(c.get("sigla") or "-")),
                    ft.DataCell(ft.Text("🟢" if ativo else "🔴")),
                    ft.DataCell(ft.Row(botoes, spacing=6)),
                ])
            )

        # Atualiza estado de ordenação no DataTable
        self.tabela.sort_column_index = self.sort.col
        self.tabela.sort_ascending    = self.sort.asc

        self.lbl_pagina.value = f"Página {self.current_page} / {total_pages}"
        self.tabela.update()
        self.lbl_pagina.update()
        self.app_page.update()


    # ======================================================
    # PAGINAÇÃO
    # ======================================================

    def proxima(self, e):
        total = len(self.clientes_filtrados)
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
        ativo = self.is_ativo(cliente)
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Cliente"),
            content=ft.Column(
                [
                    ft.Text(f"Nome: {cliente.get('nome')}"),
                    ft.Text(f"Tipo: {cliente.get('tipo')}"),
                    ft.Text(f"Documento: {cliente.get('documento')}"),
                    ft.Text(f"Sigla: {cliente.get('sigla')}"),
                    ft.Text(f"Status: {'Ativo' if ativo else 'Inativo'}",
                            color=ft.Colors.GREEN_700 if ativo else ft.Colors.RED_700,
                            weight=ft.FontWeight.W_600),
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
    # SOFT DELETE / REATIVAÇÃO
    # ======================================================
    # Mesmo padrão de pages/contratos/view.py: nunca DELETE físico
    # via UI — apenas alterna o campo "ativo". O cliente continua no
    # banco (contratos vinculados a ele permanecem íntegros) e pode
    # ser reativado a qualquer momento pela mesma tela.

    def confirmar_excluir(self, cliente):
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Confirmar exclusão"),
            content=ft.Text(
                f"Excluir o cliente '{cliente.get('nome')}'?\n\n"
                "O cliente será desativado (não aparece mais nas listagens "
                "ativas), mas pode ser reativado depois. Contratos já "
                "vinculados a ele não são afetados."
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: self._fechar_confirm(dialog)),
                ft.FilledButton(
                    "Excluir",
                    style=ft.ButtonStyle(bgcolor=ft.Colors.RED),
                    on_click=lambda e: self.app_page.run_task(self._excluir_async, cliente, dialog),
                ),
            ],
        )
        self.app_page.overlay.append(dialog)
        dialog.open = True
        self.app_page.update()

    def _fechar_confirm(self, dialog):
        dialog.open = False
        self.app_page.update()

    async def _excluir_async(self, cliente, dialog):
        try:
            resultado = await run_db(self.app_page, update_cliente, cliente["id"], {"ativo": False})
        except Exception as ex:
            dialog.open = False
            self.app_page.update()
            snack_erro(self.app_page, ex, contexto="excluir o cliente")
            return

        dialog.open = False
        self.app_page.update()

        if not resultado:
            snack_erro(self.app_page, Exception("sem resultado"), contexto="excluir o cliente")
            return

        snack_sucesso(self.app_page, f"Cliente '{cliente.get('nome')}' excluído.")
        # FIX (logs mais detalhados): inclui id, documento e sigla no
        # detalhe do log, não só o nome — facilita localizar o
        # registro exato depois, caso existam clientes com nomes
        # parecidos.
        log_acao(
            self.app_page,
            f"Cliente excluído (soft delete): '{cliente.get('nome')}'",
            f"cliente_id={cliente.get('id')} documento={cliente.get('documento') or '-'} "
            f"sigla={cliente.get('sigla') or '-'} status_anterior=ativo status_novo=inativo",
        )
        self.recarregar()

    def reativar(self, cliente):
        self.app_page.run_task(self._reativar_async, cliente)

    async def _reativar_async(self, cliente):
        try:
            resultado = await run_db(self.app_page, update_cliente, cliente["id"], {"ativo": True})
        except Exception as ex:
            snack_erro(self.app_page, ex, contexto="reativar o cliente")
            return

        if not resultado:
            snack_erro(self.app_page, Exception("sem resultado"), contexto="reativar o cliente")
            return

        snack_sucesso(self.app_page, f"Cliente '{cliente.get('nome')}' reativado.")
        log_acao(
            self.app_page,
            f"Cliente reativado: '{cliente.get('nome')}'",
            f"cliente_id={cliente.get('id')} documento={cliente.get('documento') or '-'} "
            f"sigla={cliente.get('sigla') or '-'} status_anterior=inativo status_novo=ativo",
        )
        self.recarregar()


# ======================================================
# EXPORT
# ======================================================

def clientes_view(page: ft.Page):
    return ClientesView(page)