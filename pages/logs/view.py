"""
pages/logs/view.py
====================
Tela "Logs de Auditoria" — só para administradores.

Estrutura clonada de pages/clientes/view.py (paginação 100% em
memória, comprovadamente estável).

FIX (esta versão): busca por texto agora cobre TODOS os campos
relevantes (ação, detalhes, nível traduzido, data/hora) — mesmo
padrão de busca ampla usado em pages/contratos/view.py (junta os
campos num texto único e verifica se o termo buscado está contido
nele), em vez de filtrar só pelo campo "ação".
"""

import flet as ft

from database.models import get_logs
from database.supabase_client import run_db

OPCOES_PAGE_SIZE = [10, 25, 50, 100]

CORES_NIVEL = {
    "acao": ft.Colors.BLUE,
    "erro": ft.Colors.RED,
    "sistema": ft.Colors.ORANGE,
}

LABEL_NIVEL = {"acao": "Ação", "erro": "Erro", "sistema": "Sistema"}


class LogsView(ft.Column):

    def __init__(self, page: ft.Page):
        super().__init__(expand=True, spacing=10)

        self.app_page = page
        self.tenant_id = page.local_store.get("tenant_id") if hasattr(page, "local_store") else None

        self.page_size = 25
        self.current_page = 1
        self.logs = []
        self.logs_filtrados = []

        # =========================
        # LOADING
        # =========================
        self.loading = ft.ProgressRing(visible=False, width=22, height=22, stroke_width=2)

        # =========================
        # FILTROS
        # =========================
        self.dd_nivel = ft.Dropdown(
            width=160, value="todos",
            options=[
                ft.dropdown.Option("todos"),
                ft.dropdown.Option("acao"),
                ft.dropdown.Option("erro"),
                ft.dropdown.Option("sistema"),
            ],
        )
        self.dd_nivel.on_change = self.filtrar

        self.busca = ft.TextField(
            hint_text="Buscar por ação, detalhes, data...",
            width=300,
        )
        self.busca.on_change = self.filtrar

        self.dd_page_size = ft.Dropdown(
            width=140,
            value=str(self.page_size),
            options=[ft.dropdown.Option(str(n), f"{n} por página") for n in OPCOES_PAGE_SIZE],
        )
        self.dd_page_size.on_change = self._mudar_page_size

        # =========================
        # TABELA
        # =========================
        self.tabela = ft.DataTable(
            column_spacing=14,
            heading_row_height=38,
            data_row_min_height=36,
            divider_thickness=0.5,
            columns=[
                ft.DataColumn(ft.Text("Data/Hora")),
                ft.DataColumn(ft.Text("Nível")),
                ft.DataColumn(ft.Text("Ação")),
                ft.DataColumn(ft.Text("Detalhes")),
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
                    ft.Text("Logs de Auditoria", size=22, weight=ft.FontWeight.BOLD),
                    ft.Row(
                        [
                            ft.OutlinedButton("Atualizar", height=38, on_click=self.recarregar),
                            self.loading,
                        ],
                        spacing=8,
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),

            ft.Row([self.dd_nivel, self.busca, self.dd_page_size], spacing=8, wrap=True),

            ft.Divider(height=1),

            ft.Container(
                expand=True,
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
            dados = await run_db(self.app_page, get_logs, self.tenant_id, None, None, 1000)
        except Exception as ex:
            print("Erro logs:", ex)
            dados = []

        self.logs = dados or []
        self.current_page = 1
        self.loading.visible = False
        self._aplicar_filtro()

    def recarregar(self, e=None):
        self.app_page.run_task(self._carregar_dados)


    # ======================================================
    # FILTRO / TAMANHO DE PÁGINA
    # ======================================================

    def filtrar(self, e):
        self.current_page = 1
        self._aplicar_filtro()

    def _mudar_page_size(self, e):
        try:
            self.page_size = int(self.dd_page_size.value)
        except (TypeError, ValueError):
            self.page_size = 25
        self.current_page = 1
        self.atualizar_tabela()

    def _aplicar_filtro(self):
        nivel = self.dd_nivel.value
        termo = (self.busca.value or "").lower().strip()

        lista = list(self.logs)

        if nivel and nivel != "todos":
            lista = [l for l in lista if (l.get("nivel") or "acao") == nivel]

        if termo:
            def _match(l):
                nivel_l = l.get("nivel") or "acao"
                texto = " ".join([
                    str(l.get("acao") or ""),
                    str(l.get("detalhes") or ""),
                    str(l.get("data_hora") or ""),
                    LABEL_NIVEL.get(nivel_l, nivel_l),
                ]).lower()
                return termo in texto
            lista = list(filter(_match, lista))

        self.logs_filtrados = lista
        self.atualizar_tabela()


    # ======================================================
    # TABELA
    # ======================================================

    def atualizar_tabela(self):

        self.tabela.rows.clear()

        total = len(self.logs_filtrados)
        total_pages = max(1, (total + self.page_size - 1) // self.page_size)

        ini = (self.current_page - 1) * self.page_size
        fim = ini + self.page_size

        for l in self.logs_filtrados[ini:fim]:

            nivel = l.get("nivel") or "acao"
            cor = CORES_NIVEL.get(nivel, ft.Colors.GREY)
            label_nivel = LABEL_NIVEL.get(nivel, nivel)

            data_hora = l.get("data_hora") or ""
            acao = l.get("acao") or ""
            detalhes = l.get("detalhes") or ""
            if len(detalhes) > 80:
                detalhes = detalhes[:77] + "..."

            self.tabela.rows.append(
                ft.DataRow(cells=[
                    ft.DataCell(ft.Text(str(data_hora))),
                    ft.DataCell(ft.Text(label_nivel, color=cor, weight=ft.FontWeight.BOLD)),
                    ft.DataCell(ft.Text(str(acao))),
                    ft.DataCell(ft.Text(str(detalhes))),
                ])
            )

        self.lbl_pagina.value = f"Página {self.current_page} / {total_pages} ({total} registros)"
        self.tabela.update()
        self.lbl_pagina.update()


    # ======================================================
    # PAGINAÇÃO
    # ======================================================

    def proxima(self, e):
        total = len(self.logs_filtrados)
        if self.current_page * self.page_size < total:
            self.current_page += 1
            self.atualizar_tabela()

    def anterior(self, e):
        if self.current_page > 1:
            self.current_page -= 1
            self.atualizar_tabela()


# ======================================================
# EXPORT
# ======================================================

def logs_view(page: ft.Page):
    return LogsView(page)