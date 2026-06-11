# views/relatorios_view.py
#
# Compatível com Flet 0.84.0
#
# Estrutura de tabs: ft.Tabs(content=ft.Column([TabBar, TabBarView]), length=N)
# Download: salva em ~/Downloads e abre a pasta, via FilePickerService do projeto.

from __future__ import annotations

import asyncio
import io
import os
import subprocess
import sys
from typing import Callable

import flet as ft

from app.filepicker import FilePickerService

from database.models_relatorios import (
    get_lista_clientes,
    get_relatorio_clientes,
    get_relatorio_notificacoes,
    get_relatorio_contratos,
    get_relatorio_prazos,
)
from utils.dataptbr import data_db_para_br
from utils.export_relatorios import (
    exportar_clientes_excel,  exportar_clientes_pdf,
    exportar_alertas_excel,   exportar_alertas_pdf,
    exportar_contratos_excel, exportar_contratos_pdf,
    exportar_prazos_excel,    exportar_prazos_pdf,
)
from utils.table_sort import SortState


PAGE_SIZE = 10
N_ABAS    = 4

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


# ══════════════════════════════════════════════════════════════════════
# TABELA PAGINADA GENÉRICA
# ══════════════════════════════════════════════════════════════════════

class _TabelaPaginada(ft.Column):
    def __init__(
        self,
        colunas_def: list[tuple[str, str, bool]],
        row_builder: Callable[[dict], ft.DataRow],
    ):
        super().__init__(expand=True, spacing=0)

        self._colunas_def = colunas_def
        self._row_builder = row_builder
        self._dados: list[dict] = []
        self._pagina = 1

        self.sort    = SortState(default_col=0)
        self.sort.set_callback(self._render)
        self._chaves = [c[1] for c in colunas_def]

        self.tabela = ft.DataTable(
            column_spacing=14,
            heading_row_height=38,
            divider_thickness=0.5,
            sort_column_index=self.sort.col,
            sort_ascending=self.sort.asc,
            columns=[
                ft.DataColumn(
                    ft.Text(label, weight=ft.FontWeight.BOLD),
                    numeric=num,
                    on_sort=self.sort.handler(i),
                )
                for i, (label, _, num) in enumerate(colunas_def)
            ],
            rows=[],
        )

        self.lbl_pagina = ft.Text(size=13)

        self.controls = [
            ft.Container(
                expand=True,
                height=430,
                content=ft.Column([self.tabela], scroll=ft.ScrollMode.AUTO),
            ),
            ft.Row(
                [
                    ft.OutlinedButton("Anterior", on_click=self._anterior),
                    self.lbl_pagina,
                    ft.OutlinedButton("Próxima", on_click=self._proxima),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=12,
            ),
        ]

    def set_dados(self, dados: list[dict]):
        self._dados  = dados or []
        self._pagina = 1
        self._render()

    def get_dados(self) -> list[dict]:
        return self._dados

    def _render(self):
        lista       = self.sort.apply(self._dados, self._chaves)
        total       = len(lista)
        total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        ini = (self._pagina - 1) * PAGE_SIZE
        fim = ini + PAGE_SIZE

        self.tabela.rows.clear()
        for d in lista[ini:fim]:
            self.tabela.rows.append(self._row_builder(d))

        self.tabela.sort_column_index = self.sort.col
        self.tabela.sort_ascending    = self.sort.asc
        self.lbl_pagina.value = (
            f"Página {self._pagina} / {total_pages}  •  {total} registro(s)"
        )
        try:
            self.tabela.update()
            self.lbl_pagina.update()
        except Exception:
            pass

    def _proxima(self, _e):
        if self._pagina * PAGE_SIZE < len(self._dados):
            self._pagina += 1
            self._render()

    def _anterior(self, _e):
        if self._pagina > 1:
            self._pagina -= 1
            self._render()


# ══════════════════════════════════════════════════════════════════════
# ROW BUILDERS
# ══════════════════════════════════════════════════════════════════════

def _row_cliente(d: dict) -> ft.DataRow:
    return ft.DataRow(cells=[
        ft.DataCell(ft.Text(str(d.get("id", "")))),
        ft.DataCell(ft.Text(d.get("nome",      "") or "")),
        ft.DataCell(ft.Text(d.get("tipo",      "") or "")),
        ft.DataCell(ft.Text(d.get("documento", "") or "")),
        ft.DataCell(ft.Text(d.get("sigla",     "") or "")),
    ])


def _row_alerta(d: dict) -> ft.DataRow:
    cor = ft.Colors.GREEN_700 if d.get("status") == "Enviado" else ft.Colors.RED_700
    return ft.DataRow(cells=[
        ft.DataCell(ft.Text(d.get("cliente",     "") or "")),
        ft.DataCell(ft.Text(d.get("contrato",    "") or "")),
        ft.DataCell(ft.Text(d.get("observacao",  "") or "")),
        ft.DataCell(ft.Text(data_db_para_br(d.get("inicio",      "")))),
        ft.DataCell(ft.Text(data_db_para_br(d.get("vencimento",  "")))),
        ft.DataCell(ft.Text(str(d.get("dias_antes", "")))),
        ft.DataCell(ft.Text(
            d.get("status", "") or "",
            color=cor,
            weight=ft.FontWeight.BOLD,
        )),
    ])


def _row_contrato(d: dict) -> ft.DataRow:
    return ft.DataRow(cells=[
        ft.DataCell(ft.Text(d.get("cliente",         "") or "")),
        ft.DataCell(ft.Text(d.get("nome",            "") or "")),
        ft.DataCell(ft.Text(d.get("indice",          "") or "")),
        ft.DataCell(ft.Text(data_db_para_br(d.get("data_inicial",    "")))),
        ft.DataCell(ft.Text(data_db_para_br(d.get("data_assinatura", "")))),
        ft.DataCell(ft.Text(d.get("termo_final",     "") or "")),
        ft.DataCell(ft.Text(d.get("tipo_contrato",   "") or "")),
        ft.DataCell(ft.Text(d.get("valor",           "") or "")),
        ft.DataCell(ft.Text(d.get("situacao",        "") or "")),
    ])


def _row_prazo(d: dict) -> ft.DataRow:
    return ft.DataRow(cells=[
        ft.DataCell(ft.Text(d.get("cliente",    "") or "")),
        ft.DataCell(ft.Text(d.get("contrato",   "") or "")),
        ft.DataCell(ft.Text(d.get("tipo_prazo", "") or "")),
        ft.DataCell(ft.Text(d.get("observacao", "") or "")),
        ft.DataCell(ft.Text(str(d.get("meses",  "")))),
        ft.DataCell(ft.Text(data_db_para_br(d.get("data_base",       "")))),
        ft.DataCell(ft.Text(d.get("base_tipo",  "") or "")),
        ft.DataCell(ft.Text(data_db_para_br(d.get("data_criacao",    "")))),
        ft.DataCell(ft.Text(data_db_para_br(d.get("data_vencimento", "")))),
    ])


# ══════════════════════════════════════════════════════════════════════
# VIEW PRINCIPAL
# ══════════════════════════════════════════════════════════════════════

class RelatoriosView(ft.Column):

    def __init__(self, page: ft.Page):
        super().__init__(expand=True, spacing=0)

        self.app_page  = page
        self.tenant_id = _get_tenant(page)
        self._idx      = 0          # aba ativa

        # ── FilePickerService — mesmo padrão usado no restante do projeto ──
        self._picker_svc = FilePickerService()
        self._picker_svc.register(page)

        # ── loading ────────────────────────────────────────────────
        self.loading = ft.ProgressRing(
            visible=False, width=22, height=22, stroke_width=2,
        )

        # ── filtro: cliente ────────────────────────────────────────
        self.dd_cliente = ft.Dropdown(
            width=250,
            label="Cliente",
            value="todos",
            options=[ft.dropdown.Option("todos", "Todos os clientes")],
        )

        # ── filtro: status alertas (só aba 1) ──────────────────────
        self.dd_status = ft.Dropdown(
            width=165,
            label="Status",
            value="todos",
            options=[
                ft.dropdown.Option("todos",     "Todos"),
                ft.dropdown.Option("enviados",  "Enviados"),
                ft.dropdown.Option("pendentes", "Pendentes"),
            ],
        )
        self._row_status = ft.Row(
            [ft.Text("Status:", size=13), self.dd_status],
            visible=False, spacing=6,
        )

        # ── botões ─────────────────────────────────────────────────
        self.btn_filtrar = ft.FilledButton(
            "Filtrar",
            icon=ft.Icons.FILTER_LIST,
            on_click=self._aplicar_filtro,
        )
        self.btn_excel = ft.OutlinedButton(
            "Excel",
            icon=ft.Icons.TABLE_CHART,
            on_click=self._exportar_excel,
        )
        self.btn_pdf = ft.OutlinedButton(
            "PDF",
            icon=ft.Icons.PICTURE_AS_PDF,
            on_click=self._exportar_pdf,
        )

        # ── tabelas ────────────────────────────────────────────────
        self._abas: list[_TabelaPaginada] = [
            _TabelaPaginada(
                colunas_def=[
                    ("ID",        "id",        False),
                    ("Nome",      "nome",      False),
                    ("Tipo",      "tipo",      False),
                    ("Documento", "documento", False),
                    ("Sigla",     "sigla",     False),
                ],
                row_builder=_row_cliente,
            ),
            _TabelaPaginada(
                colunas_def=[
                    ("Cliente",    "cliente",    False),
                    ("Contrato",   "contrato",   False),
                    ("Observação", "observacao", False),
                    ("Início",     "inicio",     False),
                    ("Vencimento", "vencimento", False),
                    ("Dias antes", "dias_antes", True),
                    ("Status",     "status",     False),
                ],
                row_builder=_row_alerta,
            ),
            _TabelaPaginada(
                colunas_def=[
                    ("Cliente",         "cliente",         False),
                    ("Nome",            "nome",            False),
                    ("Índice",          "indice",          False),
                    ("Data Inicial",    "data_inicial",    False),
                    ("Data Assinatura", "data_assinatura", False),
                    ("Termo Final",     "termo_final",     False),
                    ("Tipo",            "tipo_contrato",   False),
                    ("Valor",           "valor",           False),
                    ("Situação",        "situacao",        False),
                ],
                row_builder=_row_contrato,
            ),
            _TabelaPaginada(
                colunas_def=[
                    ("Cliente",    "cliente",         False),
                    ("Contrato",   "contrato",        False),
                    ("Tipo Prazo", "tipo_prazo",      False),
                    ("Observação", "observacao",      False),
                    ("Meses",      "meses",           True),
                    ("Data Base",  "data_base",       False),
                    ("Tipo Base",  "base_tipo",       False),
                    ("Criação",    "data_criacao",    False),
                    ("Vencimento", "data_vencimento", False),
                ],
                row_builder=_row_prazo,
            ),
        ]

        # ── TabBar + TabBarView (padrão Flet 0.84.0) ───────────────
        rotulos = ["Clientes", "Alertas", "Contratos", "Prazos"]

        self._tabbar = ft.TabBar(
            tabs=[ft.Tab(label=r) for r in rotulos],
            tab_alignment=ft.TabAlignment.START,
            indicator_color=ft.Colors.BLUE,
            label_color=ft.Colors.BLUE,
            unselected_label_color=ft.Colors.GREY,
        )

        self._tabview = ft.TabBarView(
            controls=[
                ft.Container(aba, padding=ft.padding.only(top=8))
                for aba in self._abas
            ],
            expand=True,
        )

        self._tabs_widget = ft.Tabs(
            content=ft.Column(
                [self._tabbar, self._tabview],
                expand=True, spacing=0,
            ),
            length=N_ABAS,
            selected_index=0,
            on_change=self._on_tab_change,
            expand=True,
        )

        # ── layout geral ───────────────────────────────────────────
        self.controls = [
            ft.Container(
                padding=ft.padding.symmetric(horizontal=4, vertical=8),
                content=ft.Row(
                    [
                        ft.Text("Relatórios", size=22, weight=ft.FontWeight.BOLD),
                        ft.Row(
                            [
                                self.dd_cliente,
                                self._row_status,
                                self.btn_filtrar,
                                ft.VerticalDivider(width=1),
                                self.btn_excel,
                                self.btn_pdf,
                                self.loading,
                            ],
                            spacing=8,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
            ),
            ft.Divider(height=1),
            ft.Container(content=self._tabs_widget, expand=True),
        ]

        self.app_page.run_task(self._init)

    # ══════════════════════════════════════════════════════════════
    # INICIALIZAÇÃO
    # ══════════════════════════════════════════════════════════════

    async def _init(self):
        self._set_loading(True)
        try:
            clientes = await asyncio.to_thread(
                get_lista_clientes, self.tenant_id,
            )
            self.dd_cliente.options = (
                [ft.dropdown.Option("todos", "Todos os clientes")]
                + [ft.dropdown.Option(str(c["id"]), c["nome"]) for c in clientes]
            )
            try:
                self.dd_cliente.update()
            except Exception:
                pass
        except Exception as ex:
            print("❌ Erro ao carregar clientes dropdown:", ex)

        await self._carregar_aba()
        self._set_loading(False)

    # ══════════════════════════════════════════════════════════════
    # CARGA
    # ══════════════════════════════════════════════════════════════

    def _cliente_id(self) -> int | None:
        v = self.dd_cliente.value
        return int(v) if v and v != "todos" else None

    async def _carregar_aba(self):
        idx        = self._idx
        cliente_id = self._cliente_id()

        try:
            if idx == 0:
                dados = await asyncio.to_thread(
                    get_relatorio_clientes, self.tenant_id, cliente_id,
                )
            elif idx == 1:
                dados = await asyncio.to_thread(
                    get_relatorio_notificacoes,
                    self.tenant_id, self.dd_status.value, cliente_id,
                )
            elif idx == 2:
                dados = await asyncio.to_thread(
                    get_relatorio_contratos, self.tenant_id, cliente_id,
                )
            else:
                dados = await asyncio.to_thread(
                    get_relatorio_prazos, self.tenant_id, cliente_id,
                )

            self._abas[idx].set_dados(dados)

        except Exception as ex:
            print(f"❌ Erro aba {idx}:", ex)
            self._snack("Erro ao buscar dados.")

    # ══════════════════════════════════════════════════════════════
    # EVENTOS
    # ══════════════════════════════════════════════════════════════

    def _on_tab_change(self, e):
        self._idx = int(e.data)
        self._row_status.visible = (self._idx == 1)
        try:
            self._row_status.update()
        except Exception:
            pass
        self.app_page.run_task(self._reload)

    def _aplicar_filtro(self, _e):
        self.app_page.run_task(self._reload)

    async def _reload(self):
        self._set_loading(True)
        await self._carregar_aba()
        self._set_loading(False)

    # ══════════════════════════════════════════════════════════════
    # EXPORTAÇÃO
    # ══════════════════════════════════════════════════════════════

    def _exportar_excel(self, _e):
        self.app_page.run_task(self._exportar_async, "excel")

    def _exportar_pdf(self, _e):
        self.app_page.run_task(self._exportar_async, "pdf")

    async def _exportar_async(self, fmt: str):
        dados = self._abas[self._idx].get_dados()
        if not dados:
            self._snack("Nenhum dado para exportar.")
            return

        self._set_loading(True)
        try:
            buf, nome = await asyncio.to_thread(
                self._gerar_arquivo, fmt, self._idx, dados,
            )
        except Exception as ex:
            print("❌ Erro ao gerar arquivo:", ex)
            self._set_loading(False)
            self._snack("Erro ao gerar o arquivo.")
            return

        self._set_loading(False)
        self._salvar(buf, nome)

    def _gerar_arquivo(
        self, fmt: str, idx: int, dados: list[dict],
    ) -> tuple[io.BytesIO, str]:
        status = self.dd_status.value
        mapa = {
            (0, "excel"): lambda: exportar_clientes_excel(dados),
            (0, "pdf"):   lambda: exportar_clientes_pdf(dados),
            (1, "excel"): lambda: exportar_alertas_excel(dados, status),
            (1, "pdf"):   lambda: exportar_alertas_pdf(dados, status),
            (2, "excel"): lambda: exportar_contratos_excel(dados),
            (2, "pdf"):   lambda: exportar_contratos_pdf(dados),
            (3, "excel"): lambda: exportar_prazos_excel(dados),
            (3, "pdf"):   lambda: exportar_prazos_pdf(dados),
        }
        return mapa[(idx, fmt)]()

    def _salvar(self, buf: io.BytesIO, nome: str):
        """
        Salva o arquivo em ~/Downloads e abre a pasta,
        usando o mesmo padrão do FilePickerService do projeto.
        """
        try:
            pasta   = os.path.join(os.path.expanduser("~"), "Downloads")
            os.makedirs(pasta, exist_ok=True)
            caminho = os.path.join(pasta, nome)
            with open(caminho, "wb") as f:
                f.write(buf.getvalue())
            try:
                if sys.platform == "win32":
                    os.startfile(pasta)
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", pasta])
                else:
                    subprocess.Popen(["xdg-open", pasta])
            except Exception:
                pass
            self._snack(f"Arquivo salvo em Downloads: {nome}")
        except Exception as ex:
            print("❌ Erro ao salvar:", ex)
            self._snack("Erro ao salvar o arquivo.")

    # ══════════════════════════════════════════════════════════════
    # HELPERS
    # ══════════════════════════════════════════════════════════════

    def _set_loading(self, visible: bool):
        self.loading.visible = visible
        try:
            self.loading.update()
        except Exception:
            pass

    def _snack(self, msg: str):
        self.app_page.snack_bar = ft.SnackBar(content=ft.Text(msg))
        self.app_page.snack_bar.open = True
        try:
            self.app_page.update()
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════
# EXPORT
# ══════════════════════════════════════════════════════════════════════

def relatorios_view(page: ft.Page) -> RelatoriosView:
    return RelatoriosView(page)