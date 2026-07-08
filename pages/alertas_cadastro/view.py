import flet as ft
import asyncio

from database.models import (
    get_contratos,
    get_clientes,
    get_tipos_prazos_db,
    add_prazo,
    get_prazos_por_contrato,
)
from database.supabase_client import run_db
from utils.dataptbr import data_br_para_db, data_db_para_br
from utils.calendario_ptbr import calendario_ptbr


def _snack(page, msg):
    page.snack_bar = ft.SnackBar(ft.Text(msg))
    page.snack_bar.open = True
    page.update()


class AlertasCadastroView(ft.Column):

    def __init__(self, page: ft.Page):
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
                border_radius=10,
                bgcolor=ft.Colors.WHITE,
                padding=8,
                content=self.lista_contratos,
            ),

            self.painel_prazo,
        ])

        page.run_task(self._carregar)

    async def _carregar(self):
        self.loading.visible = True
        self.app_page.update()

        try:
            contratos = await run_db(self.app_page, get_contratos, self.tenant_id)
            clientes  = await run_db(self.app_page, get_clientes, self.tenant_id)
        except Exception as ex:
            print("Erro alertas_cadastro:", ex)
            contratos = clientes = []

        self.contratos = contratos or []
        self.clientes_map = {c["id"]: c["nome"] for c in (clientes or [])}

        self.loading.visible = False
        self._filtrar()

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
                ft.Text("Nenhum contrato encontrado.", color=ft.Colors.GREY_500)
            )
            self.app_page.update()
            return

        for c in self.filtrados[:50]:
            sel = bool(self.selecionado and c["id"] == self.selecionado["id"])
            cli_nome = self.clientes_map.get(c.get("cliente_id"), "-")

            self.lista_contratos.controls.append(
                ft.Container(
                    padding=ft.padding.symmetric(vertical=6, horizontal=10),
                    border_radius=8,
                    bgcolor=ft.Colors.BLUE_50 if sel else ft.Colors.GREY_50,
                    border=ft.border.all(1, ft.Colors.BLUE_300 if sel else ft.Colors.GREY_200),
                    content=ft.Row([
                        ft.Column([
                            ft.Text(c.get("nome", ""), size=13),
                            ft.Text(cli_nome, size=11, color=ft.Colors.GREY_600),
                        ], expand=True),

                        ft.FilledTonalButton(
                            "Ver / + Prazo",
                            on_click=lambda e, cc=c: self.app_page.run_task(self._selecionar, cc),
                        ),
                    ]),
                )
            )

        self.app_page.update()

    async def _selecionar(self, contrato):
        self.selecionado = contrato
        self._render_lista()
        await self._build_painel(contrato)

    async def _build_painel(self, contrato):

        tipos_p = await run_db(self.app_page, get_tipos_prazos_db, self.tenant_id) or []

        # =============================
        # CAMPOS
        # =============================
        tf_dt = ft.TextField(label="Calendário", read_only=True)
        tf_ob = ft.TextField(label="Observação")

        dd_tp = ft.Dropdown(
            label="Tipo",
            options=[ft.dropdown.Option(t["nome"]) for t in tipos_p],
        )

        lbl_err = ft.Text("", color=ft.Colors.RED)

        prazos_col = ft.Column(spacing=4)

        # =============================
        # FUNÇÕES AUXILIARES
        # =============================

        def _limpar_campos():
            tf_dt.value = ""
            tf_ob.value = ""
            dd_tp.value = None
            lbl_err.value = ""

        async def _refresh_prazos():
            prazos_col.controls.clear()

            prazos = await run_db(self.app_page, get_prazos_por_contrato, contrato["id"]) or []

            if not prazos:
                prazos_col.controls.append(
                    ft.Text("Nenhum prazo cadastrado.", color=ft.Colors.GREY_500)
                )
            else:
                for p in prazos:
                    prazos_col.controls.append(
                        ft.Container(
                            content=ft.Row([
                                ft.Icon(ft.Icons.CALENDAR_TODAY, size=13),
                                ft.Text(data_db_para_br(p.get("data_vencimento"))),
                                ft.Text(p.get("observacao") or ""),
                            ])
                        )
                    )

        def cal(e):
            calendario_ptbr(
                self.app_page,
                on_select=lambda d: (
                    setattr(tf_dt, "value", d.strftime("%d/%m/%Y")),
                    self.app_page.update(),
                ),
            )

        # =============================
        # SALVAR PRAZO
        # =============================

        async def salvar(e):

            if not tf_dt.value:
                lbl_err.value = "Selecione data"
                self.app_page.update()
                return

            await run_db(
                self.app_page, add_prazo,
                contrato_id=contrato["id"],
                meses=None,
                observacao=tf_ob.value,
                data_criacao=contrato.get("data_inicial"),
                data_vencimento=data_br_para_db(tf_dt.value),
                tenant_id=self.tenant_id,
            )

            await _refresh_prazos()
            _limpar_campos()

            _snack(self.app_page, "Prazo adicionado!")
            self.app_page.update()

        def fechar(e):
            self.painel_prazo.visible = False
            self.selecionado = None
            self._render_lista()
            self.app_page.update()

        # =============================
        # PRIMEIRO CARREGAMENTO
        # =============================

        await _refresh_prazos()

        # =============================
        # UI
        # =============================

        self.painel_prazo.content = ft.Column([
            ft.Text(f"{contrato['nome']} — Prazos"),

            prazos_col,

            ft.Row([
                ft.OutlinedButton("Data", on_click=cal),
                tf_dt,
                dd_tp,
            ]),

            tf_ob,
            lbl_err,

            ft.FilledButton("Salvar", on_click=salvar),
            ft.TextButton("Fechar", on_click=fechar),
        ])

        self.painel_prazo.visible = True
        self.app_page.update()


def alertas_cadastro_view(page: ft.Page):
    return AlertasCadastroView(page)