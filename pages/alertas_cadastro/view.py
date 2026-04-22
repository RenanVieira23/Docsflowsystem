import flet as ft
import asyncio

from database.models import (
    get_contratos,
    get_clientes,
    get_tipos_prazos_db,
    add_prazo,
    get_prazos_por_contrato,
)
from utils.dataptbr import data_br_para_db, data_db_para_br
from utils.calendario_ptbr import calendario_ptbr


def _snack(page, msg):
    page.snack_bar = ft.SnackBar(ft.Text(msg))
    page.snack_bar.open = True
    page.update()


class AlertasCadastroView(ft.Column):

    def __init__(self, page: ft.Page):
        # scroll=AUTO no Column raiz para que o painel de prazo seja sempre visível
        super().__init__(expand=True, spacing=12, scroll=ft.ScrollMode.AUTO)
        self.app_page     = page
        self.tenant_id    = page.local_store.get("tenant_id") if hasattr(page, "local_store") else None
        self.contratos    = []
        self.filtrados    = []
        self.clientes_map = {}
        self.selecionado  = None

        self.loading = ft.ProgressRing(visible=False, width=18, height=18, stroke_width=2)

        self.tf_busca = ft.TextField(
            hint_text="Buscar contrato (apelido, cliente, responsável...)",
            expand=True, height=38, on_change=self._filtrar,
        )

        self.lista_contratos = ft.Column(spacing=4, scroll=ft.ScrollMode.AUTO)

        # Painel de prazo (fica visível após selecionar contrato)
        self.painel_prazo = ft.Container(visible=False)

        self.controls.extend([
            ft.Row([
                ft.Text("Cadastro de Prazos", size=22, weight=ft.FontWeight.BOLD),
                self.loading,
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),

            ft.Text(
                "Pesquise um contrato, selecione-o e gerencie seus prazos.",
                color=ft.Colors.GREY_600, size=13,
            ),

            ft.Divider(),

            ft.Row([self.tf_busca], spacing=8),

            ft.Container(
                height=260,
                border=ft.border.all(1, ft.Colors.BLACK12),
                border_radius=10, bgcolor=ft.Colors.WHITE, padding=8,
                content=self.lista_contratos,
            ),

            self.painel_prazo,
        ])

        page.run_task(self._carregar)

    # ── carregamento ────────────────────────────────────────────

    async def _carregar(self):
        self.loading.visible = True
        self.app_page.update()
        try:
            contratos = await asyncio.to_thread(get_contratos, self.tenant_id)
            clientes  = await asyncio.to_thread(get_clientes,  self.tenant_id)
        except Exception as ex:
            print("Erro alertas_cadastro:", ex)
            contratos = clientes = []
        self.contratos    = contratos or []
        self.clientes_map = {c["id"]: c["nome"] for c in (clientes or [])}
        self.loading.visible = False
        self._filtrar()

    # ── filtro ──────────────────────────────────────────────────

    def _filtrar(self, e=None):
        termo = (self.tf_busca.value or "").lower().strip()
        if termo:
            self.filtrados = [
                c for c in self.contratos
                if termo in str(c.get("nome", "")).lower()
                or termo in self.clientes_map.get(c.get("cliente_id"), "").lower()
                or termo in str(c.get("indice") or "").lower()
                or termo in str(c.get("responsavel") or "").lower()
            ]
        else:
            self.filtrados = list(self.contratos)
        self._render_lista()

    def _render_lista(self):
        self.lista_contratos.controls.clear()

        if not self.filtrados:
            self.lista_contratos.controls.append(
                ft.Text("Nenhum contrato encontrado.", color=ft.Colors.GREY_500, italic=True, size=13))
            self.lista_contratos.update()
            return

        for c in self.filtrados[:50]:
            sel      = bool(self.selecionado and c["id"] == self.selecionado["id"])
            cli_nome = self.clientes_map.get(c.get("cliente_id"), "-")

            row = ft.Container(
                padding=ft.padding.symmetric(vertical=6, horizontal=10),
                border_radius=8,
                bgcolor=ft.Colors.BLUE_50 if sel else ft.Colors.GREY_50,
                border=ft.border.all(1, ft.Colors.BLUE_300 if sel else ft.Colors.GREY_200),
                content=ft.Row([
                    ft.Column([
                        ft.Text(c.get("nome", ""), weight=ft.FontWeight.W_500, size=13),
                        ft.Text(f"{cli_nome}  •  Resp: {c.get('responsavel') or '-'}",
                                size=11, color=ft.Colors.GREY_600),
                    ], spacing=2, expand=True),
                    ft.FilledTonalButton(
                        "Ver / + Prazo", height=30,
                        on_click=lambda e, cc=c: self._selecionar(cc),
                    ),
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                on_click=lambda e, cc=c: self._selecionar(cc),
            )
            self.lista_contratos.controls.append(row)

        self.lista_contratos.update()

    # ── selecionar contrato e construir painel ───────────────────

    def _selecionar(self, contrato):
        self.selecionado = contrato
        self._render_lista()
        self._build_painel(contrato)

    def _build_painel(self, contrato):
        tid     = self.tenant_id
        tipos_p = []
        try:
            tipos_p = get_tipos_prazos_db(tid) or []
        except: pass

        # ── prazos existentes ──
        prazos_col = ft.Column(spacing=4)

        def _refresh_prazos():
            prazos_col.controls.clear()
            try:
                prazos = get_prazos_por_contrato(contrato["id"]) or []
            except: prazos = []

            if not prazos:
                prazos_col.controls.append(
                    ft.Text("Nenhum prazo cadastrado.", color=ft.Colors.GREY_500, italic=True, size=12))
            else:
                for p in prazos:
                    prazos_col.controls.append(
                        ft.Container(
                            padding=ft.padding.symmetric(vertical=4, horizontal=8),
                            border_radius=6,
                            bgcolor=ft.Colors.GREY_50,
                            border=ft.border.all(1, ft.Colors.GREY_200),
                            content=ft.Row([
                                ft.Icon(ft.Icons.CALENDAR_TODAY, size=13, color=ft.Colors.BLUE_400),
                                ft.Text(data_db_para_br(p.get("data_vencimento")),
                                        size=12, weight=ft.FontWeight.W_500),
                                ft.Text(f"— {p.get('observacao') or ''}", size=12,
                                        color=ft.Colors.GREY_600),
                            ], spacing=6),
                        )
                    )
            prazos_col.update()

        _refresh_prazos()

        # ── campos novo prazo ──
        tf_dt = ft.TextField(label="Data do prazo (DD/MM/AAAA)", width=200, read_only=True)
        tf_ob = ft.TextField(label="Observação", width=320)
        dd_tp = ft.Dropdown(
            label="Tipo de prazo", width=180,
            options=[ft.dropdown.Option(t["nome"]) for t in tipos_p],
            hint_text="Selecione..." if tipos_p else "Cadastre em Tipos",
        )
        lbl_err = ft.Text("", color=ft.Colors.RED_700, size=12)

        def cal(e):
            calendario_ptbr(self.app_page, on_select=lambda d: (
                setattr(tf_dt, "value", d.strftime("%d/%m/%Y")),
                self.app_page.update(),
            ))

        def salvar(e):
            if not tf_dt.value:
                lbl_err.value = "Selecione a data do prazo."
                self.app_page.update(); return
            dt_db = data_br_para_db(tf_dt.value)
            if not dt_db:
                lbl_err.value = "Data inválida."
                self.app_page.update(); return
            try:
                add_prazo(
                    contrato_id=contrato["id"],
                    meses=None,
                    observacao=tf_ob.value or "",
                    data_criacao=contrato.get("data_inicial"),
                    data_vencimento=dt_db,
                )
            except Exception as ex:
                lbl_err.value = f"Erro: {ex}"
                self.app_page.update(); return

            tf_dt.value = ""; tf_ob.value = ""; dd_tp.value = None; lbl_err.value = ""
            _refresh_prazos()
            _snack(self.app_page, f"Prazo adicionado ao contrato {contrato.get('nome')}!")
            self.app_page.update()

        def cancelar(e):
            self.painel_prazo.visible = False
            self.selecionado = None
            self._render_lista()
            self.app_page.update()

        self.painel_prazo.content = ft.Container(
            padding=16, border_radius=12,
            bgcolor=ft.Colors.WHITE,
            border=ft.border.all(1, ft.Colors.BLUE_200),
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.DESCRIPTION_OUTLINED, color=ft.Colors.BLUE_600),
                    ft.Text(f"{contrato.get('nome')} — Prazos",
                            weight=ft.FontWeight.W_600, size=14, expand=True),
                    ft.TextButton("Fechar", on_click=cancelar),
                ], spacing=8),

                ft.Divider(height=1),

                # Prazos existentes
                ft.Text("Prazos cadastrados:", size=12, weight=ft.FontWeight.W_500,
                        color=ft.Colors.GREY_700),
                prazos_col,

                ft.Divider(height=1),

                # Novo prazo
                ft.Text("Adicionar prazo:", size=12, weight=ft.FontWeight.W_500,
                        color=ft.Colors.GREY_700),
                ft.Row([
                    ft.OutlinedButton("📅 Selecionar data", height=36, on_click=cal),
                    tf_dt, dd_tp,
                ], spacing=10, wrap=True),
                ft.Row([tf_ob], spacing=10),
                lbl_err,
                ft.Row([
                    ft.FilledButton("Salvar prazo", on_click=salvar),
                ], spacing=12),
            ], spacing=10),
        )

        self.painel_prazo.visible = True
        self.app_page.update()


def alertas_cadastro_view(page: ft.Page):
    return AlertasCadastroView(page)