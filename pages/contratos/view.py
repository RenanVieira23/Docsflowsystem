"""
pages/contratos/view.py
========================
View de Contratos — multi-tenant.

Correções desta versão:
  - tenant_id obtido com fallback (page.local_store -> page.session) e
    revalidado a cada carregamento.
  - SEM url_target em qualquer botão.
  - Diálogo "Desativar" usa page.open()/page.close() com fallback.
  - Handlers do calendário em funções nomeadas (sem lambda+tuple+setattr).
"""

import flet as ft
import asyncio

from utils.calendario_ptbr import calendario_ptbr
from utils.dataptbr import data_db_para_br, data_br_para_db
from utils.table_sort import SortState

from database.models import (
    get_contratos,
    get_clientes,
    update_contrato,
    registrar_log,
)

from pages.contratos.form import novo_contrato_dialog


def _get_tenant(page):
    tid = None
    try:
        if hasattr(page, "local_store") and page.local_store:
            tid = page.local_store.get("tenant_id")
    except Exception:
        tid = None
    if not tid:
        try:
            tid = page.session.get("tenant_id")
        except Exception:
            pass
    return tid


def _abrir_dialog(page, dialog):
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


def _fechar_dialog(page, dialog):
    if hasattr(page, "close"):
        try:
            page.close(dialog)
            return
        except Exception:
            pass
    dialog.open = False
    page.update()


# ======================================================
# VIEW
# ======================================================

class ContratosView(ft.Column):
    def __init__(self, page: ft.Page):
        super().__init__(expand=True, spacing=0)

        self.app_page = page
        self.tenant_id = _get_tenant(page)

        self.ui_h = 36
        self.ui_btn_h = 34
        self.ui_font = 13
        self.tbl_font = 12
        self.tbl_head_h = 34
        self.tbl_row_h = 32
        self.max_w = 1180

        self.page_size = 10
        self.current_page = 1
        self.contratos = []
        self.contratos_filtrados = []
        self.clientes_map = {}
        self.status_value = "ativos"

        # Ordenação
        self.sort = SortState(default_col=0)
        self.sort.set_callback(self._render_tabela)
        self.sort_chaves = [
            "id", "nome", "_cliente", "responsavel", "valor",
            "data_assinatura", "data_inicial", "vigencia", "termo_final",
            "ativo", None,
        ]

        # =========================
        # LOADING
        # =========================
        self.loading = ft.ProgressRing(visible=False, width=18, height=18, stroke_width=2)

        # =========================
        # BUSCA
        # =========================
        self.busca = ft.TextField(
            hint_text="Buscar apelido / contrato...",
            height=self.ui_h,
            text_size=self.ui_font,
            expand=True,
        )
        self.busca.on_change = self.filtrar

        # =========================
        # FILTRO PERÍODO
        # =========================
        self.filtro_inicio = ft.TextField(
            hint_text="Início (dd/mm/aaaa)",
            width=180, read_only=True,
            height=self.ui_h, text_size=self.ui_font,
        )
        self.filtro_fim = ft.TextField(
            hint_text="Fim (dd/mm/aaaa)",
            width=180, read_only=True,
            height=self.ui_h, text_size=self.ui_font,
        )

        def _set_inicio(d):
            self.filtro_inicio.value = d.strftime("%d/%m/%Y")
            self.aplicar_filtros()
            self.app_page.update()

        def _set_fim(d):
            self.filtro_fim.value = d.strftime("%d/%m/%Y")
            self.aplicar_filtros()
            self.app_page.update()

        def escolher_inicio(e):
            calendario_ptbr(self.app_page, on_select=_set_inicio)

        def escolher_fim(e):
            calendario_ptbr(self.app_page, on_select=_set_fim)

        def _limpar_periodo(e):
            self.filtro_inicio.value = ""
            self.filtro_fim.value = ""
            self.aplicar_filtros()
            self.app_page.update()

        self.btn_inicio = ft.TextButton(
            "📅", tooltip="Selecionar início", on_click=escolher_inicio,
            style=ft.ButtonStyle(padding=ft.padding.all(4)),
        )
        self.btn_fim = ft.TextButton(
            "📅", tooltip="Selecionar fim", on_click=escolher_fim,
            style=ft.ButtonStyle(padding=ft.padding.all(4)),
        )
        self.btn_limpar_periodo = ft.TextButton(
            "Limpar período",
            on_click=_limpar_periodo,
            style=ft.ButtonStyle(padding=ft.padding.symmetric(horizontal=10, vertical=6)),
        )
        self.btn_aplicar = ft.FilledButton(
            "Aplicar", height=self.ui_btn_h, on_click=self.aplicar_click
        )

        # =========================
        # STATUS (pílulas)
        # =========================
        self.status_seg = ft.Row(spacing=0)
        self._render_status_segment()

        # =========================
        # TABELA
        # =========================
        self.tabela = ft.DataTable(
            column_spacing=22,
            heading_row_height=self.tbl_head_h,
            divider_thickness=0.5,
            data_row_min_height=self.tbl_row_h,
            data_row_max_height=self.tbl_row_h,
            sort_column_index=self.sort.col,
            sort_ascending=self.sort.asc,
            columns=[
                ft.DataColumn(ft.Text("ID",          size=self.tbl_font), on_sort=self.sort.handler(0)),
                ft.DataColumn(ft.Text("Apelido",     size=self.tbl_font), on_sort=self.sort.handler(1)),
                ft.DataColumn(ft.Text("Cliente",     size=self.tbl_font), on_sort=self.sort.handler(2)),
                ft.DataColumn(ft.Text("Responsável", size=self.tbl_font), on_sort=self.sort.handler(3)),
                ft.DataColumn(ft.Text("Valor",       size=self.tbl_font), on_sort=self.sort.handler(4)),
                ft.DataColumn(ft.Text("Assinatura",  size=self.tbl_font), on_sort=self.sort.handler(5)),
                ft.DataColumn(ft.Text("Início",      size=self.tbl_font), on_sort=self.sort.handler(6)),
                ft.DataColumn(ft.Text("Vig.",        size=self.tbl_font), on_sort=self.sort.handler(7)),
                ft.DataColumn(ft.Text("Fim",         size=self.tbl_font), on_sort=self.sort.handler(8)),
                ft.DataColumn(ft.Text("Status",      size=self.tbl_font), on_sort=self.sort.handler(9)),
                ft.DataColumn(ft.Text("Ações",       size=self.tbl_font)),
            ],
            rows=[],
        )

        self.lbl_pagina = ft.Text(size=12)

        # =========================
        # LAYOUT
        # =========================
        header = ft.Row(
            [
                ft.Text("Contratos", size=24, weight=ft.FontWeight.BOLD),
                ft.Row([
                    ft.FilledButton("Novo", height=self.ui_btn_h, on_click=self.novo_contrato),
                    ft.OutlinedButton("Atualizar", height=self.ui_btn_h, on_click=self.recarregar),
                    self.loading,
                ], spacing=8),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        periodo_group = ft.Row(
            [
                ft.Text("Período:", size=12, color=ft.Colors.BLACK87),
                self.btn_inicio, self.filtro_inicio,
                self.btn_fim, self.filtro_fim,
            ],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        actions_group = ft.Row(
            [self.btn_limpar_periodo, self.btn_aplicar],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.END,
        )

        filtros_card = ft.Container(
            padding=12,
            border=ft.border.all(1, ft.Colors.BLACK12),
            border_radius=12,
            bgcolor=ft.Colors.WHITE,
            content=ft.Column(
                [
                    ft.Text("Filtros", size=12, weight=ft.FontWeight.W_600, color=ft.Colors.BLACK87),
                    ft.Container(height=8),
                    ft.ResponsiveRow(
                        spacing=12, run_spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Container(col={"xs": 12, "md": 8}, content=self.busca),
                            ft.Container(col={"xs": 12, "md": 4},
                                content=ft.Row([self.status_seg],
                                    alignment=ft.MainAxisAlignment.END,
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER)),
                        ],
                    ),
                    ft.Container(height=10),
                    ft.ResponsiveRow(
                        spacing=12, run_spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Container(col={"xs": 12, "md": 8}, content=periodo_group),
                            ft.Container(col={"xs": 12, "md": 4}, content=actions_group),
                        ],
                    ),
                ],
                spacing=0, tight=True,
            ),
        )

        tabela_card = ft.Container(
            expand=True, padding=8,
            border=ft.border.all(1, ft.Colors.BLACK12),
            border_radius=12, bgcolor=ft.Colors.WHITE,
            content=ft.Column([self.tabela], expand=True, tight=True, scroll=ft.ScrollMode.AUTO),
        )

        paginacao = ft.Row(
            [
                ft.TextButton("Anterior", on_click=self.anterior),
                self.lbl_pagina,
                ft.TextButton("Próxima", on_click=self.proxima),
            ],
            alignment=ft.MainAxisAlignment.CENTER, spacing=12,
        )

        central = ft.Container(
            width=self.max_w, expand=True,
            content=ft.Column(
                [
                    header, ft.Container(height=14),
                    filtros_card, ft.Container(height=14),
                    tabela_card, ft.Container(height=10),
                    paginacao, ft.Container(height=10),
                ],
                expand=True, spacing=0,
            ),
        )

        self.controls.append(
            ft.Row([central], expand=True, alignment=ft.MainAxisAlignment.CENTER)
        )

        self.app_page.run_task(self._carregar_dados)

    # ======================================================
    # STATUS UI
    # ======================================================

    def _set_status(self, val: str):
        self.status_value = val
        self._render_status_segment()
        self.aplicar_filtros()
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
            height=self.ui_btn_h, border=ft.border.all(1, ft.Colors.BLACK26),
            border_radius=radius, bgcolor=bg,
            padding=ft.padding.symmetric(horizontal=16),
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

    # ======================================================
    # NORMALIZA ATIVO
    # ======================================================

    def is_ativo(self, contrato):
        v = contrato.get("ativo")
        if isinstance(v, bool): return v
        if isinstance(v, str):  return v.lower() in ("true", "t", "1", "yes")
        if isinstance(v, int):  return v == 1
        return True

    def aplicar_click(self, e):
        self.aplicar_filtros()

    # ======================================================
    # CARREGAMENTO
    # ======================================================

    async def _carregar_dados(self):
        self.loading.visible = True
        self.app_page.update()

        try:
            self.tenant_id = _get_tenant(self.app_page)

            if not self.tenant_id:
                print("❌ tenant_id não encontrado")
                contratos = []
                clientes = []
            else:
                contratos = await asyncio.to_thread(get_contratos, self.tenant_id)
                clientes  = await asyncio.to_thread(get_clientes,  self.tenant_id)

        except Exception as ex:
            print("Erro contratos:", ex)
            contratos = []
            clientes = []

        self.contratos = contratos or []
        self.clientes_map = {c["id"]: c["nome"] for c in (clientes or [])}

        self.loading.visible = False
        self.aplicar_filtros()

    def recarregar(self, e=None):
        self.app_page.run_task(self._carregar_dados)

    # ======================================================
    # FILTROS
    # ======================================================

    def aplicar_filtros(self):
        contratos = list(self.contratos)

        status = (self.status_value or "ativos").strip()
        if status == "ativos":
            contratos = [c for c in contratos if self.is_ativo(c)]
        elif status == "inativos":
            contratos = [c for c in contratos if not self.is_ativo(c)]

        di = data_br_para_db(self.filtro_inicio.value or "")
        df = data_br_para_db(self.filtro_fim.value or "")
        if di or df:
            def _in_periodo(c):
                d = c.get("data_inicial") or ""
                if not d: return False
                if di and d < di: return False
                if df and d > df: return False
                return True
            contratos = [c for c in contratos if _in_periodo(c)]

        termo = (self.busca.value or "").lower().strip()
        if termo:
            def match(c):
                cliente = self.clientes_map.get(c.get("cliente_id"), "").lower()
                texto = " ".join([
                    str(c.get("id", "")), str(c.get("nome", "")), cliente,
                    str(c.get("valor", "")), str(c.get("responsavel", "")),
                    str(c.get("data_assinatura", "")), str(c.get("vigencia", "")),
                    str(c.get("data_inicial", "")), str(c.get("termo_final", "")),
                    "ativo" if self.is_ativo(c) else "inativo",
                ]).lower()
                return termo in texto
            contratos = list(filter(match, contratos))

        for c in contratos:
            c["_cliente"] = self.clientes_map.get(c.get("cliente_id"), "")

        self.contratos_filtrados = contratos
        self.current_page = 1
        self._render_tabela()

    def filtrar(self, e):
        self.aplicar_filtros()

    # ======================================================
    # TABELA
    # ======================================================

    def _render_tabela(self):
        self.tabela.rows.clear()

        lista = self.sort.apply(self.contratos_filtrados, self.sort_chaves)

        total = len(lista)
        total_pages = max(1, (total + self.page_size - 1) // self.page_size)

        ini = (self.current_page - 1) * self.page_size
        fim = ini + self.page_size

        for i, c in enumerate(lista[ini:fim]):
            ativo  = self.is_ativo(c)
            status = "🟢" if ativo else "🔴"

            botoes = [
                ft.TextButton("Ver",    on_click=lambda e, cc=c: self.ver(cc)),
                ft.TextButton("Editar", on_click=lambda e, cc=c: self.editar(cc)),
            ]
            if ativo:
                botoes.append(ft.TextButton("Desativar",
                    style=ft.ButtonStyle(color=ft.Colors.RED),
                    on_click=lambda e, cc=c: self.confirmar_desativar(cc)))
            else:
                botoes.append(ft.TextButton("Reativar",
                    style=ft.ButtonStyle(color=ft.Colors.GREEN),
                    on_click=lambda e, cc=c: self.reativar(cc)))

            row_bg = ft.Colors.with_opacity(0.03, ft.Colors.BLACK) if (i % 2 == 1) else None

            self.tabela.rows.append(
                ft.DataRow(color=row_bg, cells=[
                    ft.DataCell(ft.Text(str(c.get("id", "")),                           size=self.tbl_font)),
                    ft.DataCell(ft.Text(c.get("nome", ""),                              size=self.tbl_font)),
                    ft.DataCell(ft.Text(self.clientes_map.get(c.get("cliente_id"), "-"), size=self.tbl_font)),
                    ft.DataCell(ft.Text(c.get("responsavel") or "-",                    size=self.tbl_font)),
                    ft.DataCell(ft.Text(f"R$ {c.get('valor') or '-'}",                  size=self.tbl_font)),
                    ft.DataCell(ft.Text(data_db_para_br(c.get("data_assinatura")) or "-", size=self.tbl_font)),
                    ft.DataCell(ft.Text(data_db_para_br(c.get("data_inicial")) or "-",  size=self.tbl_font)),
                    ft.DataCell(ft.Text(str(c.get("vigencia") or "-"),                  size=self.tbl_font)),
                    ft.DataCell(ft.Text(data_db_para_br(c.get("termo_final")) or "-",   size=self.tbl_font)),
                    ft.DataCell(ft.Text(status,                                         size=self.tbl_font)),
                    ft.DataCell(ft.Row(botoes, spacing=4)),
                ])
            )

        self.tabela.sort_column_index = self.sort.col
        self.tabela.sort_ascending    = self.sort.asc
        self.lbl_pagina.value = f"Página {self.current_page} / {total_pages}"
        self.tabela.update()
        self.lbl_pagina.update()

    def atualizar_tabela(self):
        self._render_tabela()

    # ======================================================
    # PAGINAÇÃO
    # ======================================================

    def proxima(self, e):
        if self.current_page * self.page_size < len(self.contratos_filtrados):
            self.current_page += 1
            self._render_tabela()

    def anterior(self, e):
        if self.current_page > 1:
            self.current_page -= 1
            self._render_tabela()

    # ======================================================
    # CRUD
    # ======================================================

    def novo_contrato(self, e):
        novo_contrato_dialog(self.app_page, self.recarregar)

    def editar(self, contrato):
        from pages.contratos.form import editar_contrato_dialog
        editar_contrato_dialog(self.app_page, contrato, self.recarregar)

    def ver(self, contrato):
        from pages.contratos.form import ver_contrato_dialog
        ver_contrato_dialog(self.app_page, contrato, self.clientes_map)

    async def _log_async(self, acao, nome):
        try:
            usuario = None
            try:
                if hasattr(self.app_page, "local_store") and self.app_page.local_store:
                    usuario = self.app_page.local_store.get("usuario_id")
            except Exception:
                usuario = None
            if not usuario:
                try:
                    usuario = self.app_page.session.get("usuario_id")
                except Exception:
                    usuario = None
            if usuario:
                await asyncio.to_thread(registrar_log, usuario, acao, nome)
        except Exception:
            pass

    def confirmar_desativar(self, contrato):
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Confirmar"),
            content=ft.Text(f"Desativar o contrato {contrato.get('nome')}?"),
            actions=[
                ft.TextButton("Cancelar",   on_click=lambda e: _fechar_dialog(self.app_page, dialog)),
                ft.FilledButton("Desativar", on_click=lambda e: self.desativar(contrato, dialog)),
            ],
        )
        _abrir_dialog(self.app_page, dialog)

    async def _desativar_async(self, contrato, dialog):
        try:
            await asyncio.to_thread(update_contrato, contrato["id"], {"ativo": False})
            await self._log_async("Desativou contrato", contrato["nome"])
        except Exception as ex:
            print("Erro desativar:", ex)
        _fechar_dialog(self.app_page, dialog)
        self.recarregar()

    def desativar(self, contrato, dialog):
        self.app_page.run_task(self._desativar_async, contrato, dialog)

    async def _reativar_async(self, contrato):
        try:
            await asyncio.to_thread(update_contrato, contrato["id"], {"ativo": True})
            await self._log_async("Reativou contrato", contrato["nome"])
        except Exception as ex:
            print("Erro reativar:", ex)
        self.recarregar()

    def reativar(self, contrato):
        self.app_page.run_task(self._reativar_async, contrato)


# ======================================================
# EXPORT
# ======================================================

def contratos_view(page: ft.Page):
    return ContratosView(page)