"""
pages/logs/view.py
====================
Tela "Logs de Auditoria" — só para administradores.

Lista as ações registradas na tabela `logs` (login, cadastro, edição,
exclusão, erros) do tenant, com filtro por nível/usuário/texto e
paginação real no banco (não carrega o histórico inteiro em memória).

FIX (esta versão): a "badge" colorida de nível (Container + Text)
foi trocada por um texto colorido simples — mesmo padrão já usado e
comprovadamente estável em pages/painel/view.py (coluna Status). Isso
elimina qualquer suspeita de que o Container aninhado estivesse
relacionado ao erro client-side "NoSuchMethodError" relatado ao abrir
esta tela.
"""

import flet as ft

from database.models import get_logs, get_usuarios_do_tenant
from database.supabase_client import run_db
from utils.erros_ui import banner_erro_carregamento

PAGE_SIZE = 25

CORES_NIVEL = {
    "acao": ft.Colors.BLUE_700,
    "erro": ft.Colors.RED_700,
    "sistema": ft.Colors.AMBER_800,
}

LABEL_NIVEL = {"acao": "Ação", "erro": "Erro", "sistema": "Sistema"}


def _update_seguro(control):
    """Chama .update() só se o controle já estiver anexado à página —
    evita erro ao atualizar algo ainda não montado."""
    try:
        if getattr(control, "page", None):
            control.update()
    except Exception:
        pass


class LogsView(ft.Column):

    def __init__(self, page: ft.Page):
        super().__init__(expand=True, spacing=12)

        self.app_page = page
        self.tenant_id = page.local_store.get("tenant_id") if hasattr(page, "local_store") else None

        self.offset = 0
        self.total = 0
        self.usuarios_map = {}
        self._erro_carregamento = False

        self.loading = ft.ProgressRing(visible=False, width=20, height=20, stroke_width=2)
        self.area_erro = ft.Container(visible=False)

        self.tf_busca = ft.TextField(
            hint_text="Buscar por ação...", width=260, height=38,
        )

        self.dd_nivel = ft.Dropdown(
            width=160, value="todos",
            options=[
                ft.dropdown.Option("todos", "Todos os níveis"),
                ft.dropdown.Option("acao", "Ação"),
                ft.dropdown.Option("erro", "Erro"),
                ft.dropdown.Option("sistema", "Sistema"),
            ],
        )

        self.dd_usuario = ft.Dropdown(
            width=220, value="todos",
            options=[ft.dropdown.Option("todos", "Todos os usuários")],
        )

        self.btn_filtrar = ft.FilledButton("Filtrar", on_click=self._filtrar)

        self.tabela = ft.DataTable(
            column_spacing=16,
            heading_row_height=36,
            data_row_min_height=36,
            divider_thickness=0.5,
            columns=[
                ft.DataColumn(ft.Text("Data/Hora")),
                ft.DataColumn(ft.Text("Usuário")),
                ft.DataColumn(ft.Text("Nível")),
                ft.DataColumn(ft.Text("Ação")),
                ft.DataColumn(ft.Text("Detalhes")),
            ],
            rows=[],
        )

        self.lbl_pagina = ft.Text(size=12)

        self.controls.extend([
            ft.Row(
                [
                    ft.Text("Logs de Auditoria", size=22, weight=ft.FontWeight.BOLD),
                    ft.Row(
                        [
                            ft.OutlinedButton("Atualizar", height=36, on_click=self.recarregar),
                            self.loading,
                        ],
                        spacing=8,
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),

            ft.Text(
                "Histórico de ações realizadas no sistema (login, cadastros, edições, "
                "exclusões e erros). Visível apenas para administradores.",
                size=12, color=ft.Colors.GREY_600,
            ),

            ft.Row(
                [self.tf_busca, self.dd_nivel, self.dd_usuario, self.btn_filtrar],
                spacing=10, wrap=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),

            ft.Divider(),

            self.area_erro,

            ft.Container(
                expand=True,
                content=ft.Column([self.tabela], scroll=ft.ScrollMode.AUTO),
            ),

            ft.Row(
                [
                    ft.TextButton("Anterior", on_click=self._anterior),
                    self.lbl_pagina,
                    ft.TextButton("Próxima", on_click=self._proxima),
                ],
                alignment=ft.MainAxisAlignment.CENTER, spacing=16,
            ),
        ])

        page.run_task(self._init)

    # ======================================================
    # INIT
    # ======================================================

    async def _init(self):
        if self.app_page.route != "/logs":
            return

        try:
            usuarios = await run_db(self.app_page, get_usuarios_do_tenant, self.tenant_id) or []
        except Exception as ex:
            print("Erro ao carregar usuários para filtro de logs:", ex)
            usuarios = []

        if self.app_page.route != "/logs":
            return

        self.usuarios_map = {u["id"]: u.get("usuario", f"#{u['id']}") for u in usuarios}
        self.dd_usuario.options = (
            [ft.dropdown.Option("todos", "Todos os usuários")]
            + [ft.dropdown.Option(str(u["id"]), u.get("usuario", f"#{u['id']}")) for u in usuarios]
        )
        _update_seguro(self.dd_usuario)

        await self._carregar()

    # ======================================================
    # CARREGAMENTO
    # ======================================================

    async def _carregar(self):
        if self.app_page.route != "/logs":
            return

        self.loading.visible = True
        self._erro_carregamento = False
        self.app_page.update()

        nivel = self.dd_nivel.value
        usuario_id = int(self.dd_usuario.value) if self.dd_usuario.value != "todos" else None
        busca = (self.tf_busca.value or "").strip() or None

        try:
            linhas, total = await run_db(
                self.app_page, get_logs,
                self.tenant_id, nivel, usuario_id, busca, PAGE_SIZE, self.offset,
            )
        except Exception as ex:
            print("Erro ao carregar logs:", ex)
            linhas, total = [], 0
            self._erro_carregamento = True

        if self.app_page.route != "/logs":
            return

        self.total = total
        self.loading.visible = False

        self.area_erro.visible = self._erro_carregamento
        if self._erro_carregamento:
            self.area_erro.content = banner_erro_carregamento(
                "os logs", on_retry=lambda e: self.app_page.run_task(self._carregar)
            )

        self._render_tabela(linhas)

    def recarregar(self, e=None):
        self.offset = 0
        self.app_page.run_task(self._carregar)

    def _filtrar(self, e=None):
        self.offset = 0
        self.app_page.run_task(self._carregar)

    # ======================================================
    # TABELA
    # ======================================================

    def _render_tabela(self, linhas: list[dict]):
        if self.app_page.route != "/logs":
            return

        self.tabela.rows.clear()

        for l in linhas:
            nivel = l.get("nivel") or "acao"
            cor_txt = CORES_NIVEL.get(nivel, ft.Colors.GREY_700)
            usuario_nome = self.usuarios_map.get(l.get("usuario_id"), "-") if l.get("usuario_id") else "-"

            detalhes = l.get("detalhes") or ""
            detalhes_curto = detalhes if len(detalhes) <= 60 else detalhes[:57] + "..."

            self.tabela.rows.append(
                ft.DataRow(cells=[
                    ft.DataCell(ft.Text(l.get("data_hora") or "-", size=12)),
                    ft.DataCell(ft.Text(usuario_nome, size=12)),
                    ft.DataCell(ft.Text(
                        LABEL_NIVEL.get(nivel, nivel), size=12,
                        color=cor_txt, weight=ft.FontWeight.BOLD,
                    )),
                    ft.DataCell(ft.Text(l.get("acao") or "-", size=12)),
                    ft.DataCell(ft.Text(detalhes_curto, size=12)),
                ])
            )

        total_pages = max(1, (self.total + PAGE_SIZE - 1) // PAGE_SIZE)
        pagina_atual = (self.offset // PAGE_SIZE) + 1
        self.lbl_pagina.value = f"Página {pagina_atual} / {total_pages} — {self.total} registro(s)"

        _update_seguro(self.tabela)
        _update_seguro(self.lbl_pagina)
        self.app_page.update()

    # ======================================================
    # PAGINAÇÃO
    # ======================================================

    def _proxima(self, e):
        if self.offset + PAGE_SIZE < self.total:
            self.offset += PAGE_SIZE
            self.app_page.run_task(self._carregar)

    def _anterior(self, e):
        if self.offset > 0:
            self.offset = max(0, self.offset - PAGE_SIZE)
            self.app_page.run_task(self._carregar)


def logs_view(page: ft.Page):
    return LogsView(page)