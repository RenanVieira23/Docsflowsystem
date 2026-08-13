import flet as ft
import asyncio

from database.models import (
    get_contratos,
    get_clientes,
    get_tipos_prazos_db,
    add_prazo,
    get_prazos_por_contrato,
    get_nomes_partes_por_contrato,
)

from database.supabase_client import run_db
from utils.dataptbr import data_br_para_db, data_db_para_br, somar_meses
from utils.calendario_ptbr import calendario_ptbr
from utils.permissoes import pode
from utils.erros_ui import snack_erro, snack_sucesso, banner_erro_carregamento
from pages.contratos.form import ver_contrato_dialog


class AlertasCadastroView(ft.Column):

    def __init__(self, page: ft.Page):
        super().__init__(
            expand=True,
            spacing=12,
            scroll=ft.ScrollMode.AUTO
        )

        self.app_page = page
        self.tenant_id = (
            page.local_store.get("tenant_id")
            if hasattr(page, "local_store")
            else None
        )

        self.contratos = []
        self.filtrados = []
        self.clientes_map = {}
        self.partes_map = {}
        self.selecionado = None
        self._erro_carregamento = False

        self.loading = ft.ProgressRing(
            visible=False,
            width=18,
            height=18,
            stroke_width=2
        )

        self.area_erro = ft.Container(visible=False)

        self.tf_busca = ft.TextField(
            hint_text="Buscar por contrato, cliente, parte vinculada, cláusula...",
            expand=True,
            height=38,
            on_change=self._filtrar,
        )

        self.lista_contratos = ft.Column(
            spacing=4,
            scroll=ft.ScrollMode.AUTO
        )

        self.painel_prazo = ft.Container(
            visible=False
        )

        self.controls.extend([
            ft.Row(
                [
                    ft.Text(
                        "Cadastro de Prazos",
                        size=22,
                        weight=ft.FontWeight.BOLD
                    ),
                    self.loading,
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN
            ),

            ft.Text(
                "Pesquise um contrato, selecione-o e gerencie seus prazos.",
                color=ft.Colors.GREY_600,
                size=13,
            ),

            ft.Divider(),

            self.area_erro,

            ft.Row(
                [self.tf_busca],
                spacing=8
            ),

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
        self._erro_carregamento = False
        self.app_page.update()

        try:
            contratos, clientes, partes_map = await asyncio.gather(
                run_db(
                    self.app_page,
                    get_contratos,
                    self.tenant_id
                ),
                run_db(
                    self.app_page,
                    get_clientes,
                    self.tenant_id
                ),
                run_db(
                    self.app_page,
                    get_nomes_partes_por_contrato,
                    self.tenant_id
                ),
            )

        except Exception as ex:
            print("Erro alertas_cadastro:", ex)

            contratos = clientes = []
            partes_map = {}
            self._erro_carregamento = True

        self.contratos = contratos or []

        self.clientes_map = {
            c["id"]: c["nome"]
            for c in (clientes or [])
        }

        self.partes_map = partes_map or {}

        self.loading.visible = False

        self.area_erro.visible = self._erro_carregamento
        if self._erro_carregamento:
            self.area_erro.content = banner_erro_carregamento(
                "os contratos", on_retry=lambda e: self.app_page.run_task(self._carregar)
            )

        self._filtrar()

    def _filtrar(self, e=None):
        termo = (
            self.tf_busca.value or ""
        ).lower().strip()

        if termo:

            def match(c):
                partes = self.partes_map.get(
                    c.get("id"),
                    ""
                ).lower()

                texto = " ".join([
                    str(c.get("id", "")),
                    str(c.get("nome", "")),
                    self.clientes_map.get(
                        c.get("cliente_id"),
                        ""
                    ),
                    str(c.get("indice") or ""),
                    str(c.get("responsavel") or ""),
                    str(c.get("tipo_contrato") or ""),
                    str(c.get("clausulas") or ""),
                    partes,
                ]).lower()

                return termo in texto

            self.filtrados = [
                c for c in self.contratos
                if match(c)
            ]

        else:
            self.filtrados = list(
                self.contratos
            )

        self._render_lista()

    def _render_lista(self):
        self.lista_contratos.controls.clear()

        if not self.filtrados:
            self.lista_contratos.controls.append(
                ft.Text(
                    "Nenhum contrato encontrado.",
                    color=ft.Colors.GREY_500
                )
            )

            self.app_page.update()
            return

        for c in self.filtrados[:50]:

            sel = bool(
                self.selecionado
                and c["id"] == self.selecionado["id"]
            )

            cli_nome = self.clientes_map.get(
                c.get("cliente_id"),
                "-"
            )

            identificador = (
                c.get("indice")
                or "-"
            )

            self.lista_contratos.controls.append(
                ft.Container(
                    padding=ft.padding.symmetric(
                        vertical=6,
                        horizontal=10
                    ),
                    border_radius=8,
                    bgcolor=(
                        ft.Colors.BLUE_50
                        if sel
                        else ft.Colors.GREY_50
                    ),
                    border=ft.border.all(
                        1,
                        (
                            ft.Colors.BLUE_300
                            if sel
                            else ft.Colors.GREY_200
                        )
                    ),
                    content=ft.Row([
                        ft.Column(
                            [
                                ft.Row(
                                    [
                                        ft.Text(
                                            c.get(
                                                "nome",
                                                ""
                                            ),
                                            size=13,
                                            weight=ft.FontWeight.W_600
                                        ),

                                        ft.Container(
                                            padding=ft.padding.symmetric(
                                                horizontal=6,
                                                vertical=1
                                            ),
                                            border_radius=4,
                                            bgcolor=ft.Colors.BLUE_100,
                                            content=ft.Text(
                                                f"Identificador: {identificador}",
                                                size=10,
                                                color=ft.Colors.BLUE_900,
                                            ),
                                        ),
                                    ],
                                    spacing=8
                                ),

                                ft.Text(
                                    cli_nome,
                                    size=11,
                                    color=ft.Colors.GREY_600
                                ),
                            ],
                            expand=True,
                            spacing=2
                        ),

                        ft.TextButton(
                            "Detalhes",
                            icon=ft.Icons.INFO_OUTLINE,
                            on_click=lambda e, cc=c:
                                self.app_page.run_task(
                                    ver_contrato_dialog,
                                    self.app_page,
                                    cc,
                                    self.clientes_map
                                ),
                        ),

                        ft.FilledTonalButton(
                            "Ver / + Prazo",
                            on_click=lambda e, cc=c:
                                self.app_page.run_task(
                                    self._selecionar,
                                    cc
                                ),
                        ),
                    ]),
                )
            )

        self.app_page.update()

    async def _selecionar(self, contrato):
        self.selecionado = contrato

        self._render_lista()

        await self._build_painel(
            contrato
        )

    async def _build_painel(self, contrato):

        try:
            tipos_p = await run_db(
                self.app_page,
                get_tipos_prazos_db,
                self.tenant_id
            ) or []
        except Exception as ex:
            snack_erro(self.app_page, ex, contexto="carregar os tipos de prazo")
            tipos_p = []

        # =============================
        # CAMPOS
        # =============================

        def cal(e):

            def _on_pick(d):
                tf_inicio.value = d.strftime(
                    "%d/%m/%Y"
                )

                _recalcular_data()

            calendario_ptbr(
                self.app_page,
                on_select=_on_pick
            )

        tf_inicio = ft.TextField(
            label="Data Início",
            read_only=True,
            width=150,
            prefix_icon=ft.Icons.CALENDAR_TODAY,
            on_click=cal,
        )

        tf_meses = ft.TextField(
            label="Meses",
            width=90,
            input_filter=ft.NumbersOnlyInputFilter(),
            keyboard_type=ft.KeyboardType.NUMBER,
        )

        # Calculada automaticamente
        # Data Início + Meses
        tf_dt = ft.TextField(
            label="Data",
            read_only=True,
            width=150
        )

        tf_ob = ft.TextField(
            label="Observação",
            expand=True
        )

        dd_tp = ft.Dropdown(
            label="Tipo",
            width=220,
            menu_width=280,
            options=[
                ft.dropdown.Option(
                    t["nome"]
                )
                for t in tipos_p
            ],
        )

        lbl_err = ft.Text(
            "",
            color=ft.Colors.RED
        )

        prazos_col = ft.Column(
            spacing=4
        )

        # =============================
        # LOADING DO SALVAMENTO
        # =============================

        loading_salvar = ft.ProgressRing(
            width=16,
            height=16,
            stroke_width=2,
            visible=False,
        )

        # O botão precisa ser uma variável
        # para podermos desabilitá-lo durante
        # o salvamento.
        btn_salvar = ft.FilledButton(
            "Salvar",
        )

        # =============================
        # FUNÇÕES AUXILIARES
        # =============================

        def _recalcular_data(e=None):

            if len(
                tf_meses.value or ""
            ) > 3:
                tf_meses.value = (
                    tf_meses.value[:3]
                )

            iso_inicio = data_br_para_db(
                tf_inicio.value
            )

            nova = somar_meses(
                iso_inicio,
                tf_meses.value
            )

            tf_dt.value = (
                data_db_para_br(nova)
                if nova
                else ""
            )

            self.app_page.update()

        tf_meses.on_change = (
            _recalcular_data
        )

        def _limpar_campos():

            tf_inicio.value = ""
            tf_meses.value = ""
            tf_dt.value = ""
            tf_ob.value = ""
            dd_tp.value = None
            lbl_err.value = ""

        async def _refresh_prazos():

            prazos_col.controls.clear()

            try:
                prazos = await run_db(
                    self.app_page,
                    get_prazos_por_contrato,
                    contrato["id"]
                ) or []
            except Exception as ex:
                snack_erro(self.app_page, ex, contexto="carregar os prazos do contrato")
                prazos = []

            if not prazos:

                prazos_col.controls.append(
                    ft.Text(
                        "Nenhum prazo cadastrado.",
                        color=ft.Colors.GREY_500
                    )
                )

            else:

                for p in prazos:

                    prazos_col.controls.append(
                        ft.Container(
                            content=ft.Row([
                                ft.Icon(
                                    ft.Icons.CALENDAR_TODAY,
                                    size=13
                                ),

                                ft.Text(
                                    data_db_para_br(
                                        p.get(
                                            "data_criacao"
                                        )
                                    ),
                                    size=12,
                                    color=ft.Colors.GREY_600
                                ),

                                ft.Text(
                                    "→",
                                    size=12,
                                    color=ft.Colors.GREY_400
                                ),

                                ft.Text(
                                    f"{p.get('meses') or 0} meses",
                                    size=12,
                                    color=ft.Colors.GREY_600
                                ),

                                ft.Text(
                                    "=",
                                    size=12,
                                    color=ft.Colors.GREY_400
                                ),

                                ft.Text(
                                    data_db_para_br(
                                        p.get(
                                            "data_vencimento"
                                        )
                                    ),
                                    weight=ft.FontWeight.W_600
                                ),

                                ft.Text(
                                    p.get("tipo") or "-",
                                    size=12,
                                    color=ft.Colors.BLUE_700,
                                    weight=ft.FontWeight.W_600
                                ),

                                ft.Text(
                                    p.get(
                                        "observacao"
                                    ) or ""
                                ),
                            ])
                        )
                    )

        # =============================
        # SALVAR PRAZO
        # =============================

        async def salvar(e):

            # =====================================
            # PROTEÇÃO CONTRA DUPLO CLIQUE
            # =====================================

            if btn_salvar.disabled:
                return

            # =====================================
            # VALIDAÇÕES
            # =====================================

            if not tf_inicio.value:

                lbl_err.value = (
                    "Selecione a Data Início"
                )

                self.app_page.update()

                return

            if not tf_meses.value:

                lbl_err.value = (
                    "Informe os meses"
                )

                self.app_page.update()

                return

            if not tf_dt.value:

                lbl_err.value = (
                    "Não foi possível calcular a data "
                    "— confira Data Início e Meses"
                )

                self.app_page.update()

                return

            # =====================================
            # INICIA LOADING
            # =====================================

            btn_salvar.disabled = True

            loading_salvar.visible = True

            lbl_err.value = ""

            self.app_page.update()

            # =====================================
            # SALVAMENTO
            # =====================================

            try:

                await run_db(
                    self.app_page,
                    add_prazo,

                    contrato_id=contrato["id"],

                    meses=int(
                        tf_meses.value
                    ),

                    observacao=tf_ob.value,

                    data_criacao=data_br_para_db(
                        tf_inicio.value
                    ),

                    data_vencimento=data_br_para_db(
                        tf_dt.value
                    ),

                    tenant_id=self.tenant_id,

                    tipo=dd_tp.value,
                )

                # Atualiza a lista de prazos
                await _refresh_prazos()

                # Limpa os campos
                _limpar_campos()

                # Mensagem de sucesso
                snack_sucesso(
                    self.app_page,
                    "Prazo adicionado!"
                )

            except Exception as ex:

                print(
                    "Erro ao salvar prazo:",
                    ex
                )

                snack_erro(self.app_page, ex, contexto="salvar o prazo")

            finally:

                # =====================================
                # FINALIZA LOADING
                # =====================================

                # Isso será executado tanto em caso
                # de sucesso quanto em caso de erro.

                btn_salvar.disabled = False

                loading_salvar.visible = False

                self.app_page.update()

        # Agora vinculamos a função salvar
        # ao botão depois que ela foi criada.
        btn_salvar.on_click = salvar

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

        pode_cadastrar = pode(
            self.app_page,
            "prazos",
            "cadastrar"
        )

        formulario = ft.Column(
            [
                ft.Text(
                    "Cálculo automático: Data = Data Início + Meses",
                    size=11,
                    color=ft.Colors.GREY_500,
                    italic=True
                ),

                ft.Row(
                    [
                        tf_inicio,
                        tf_meses,
                        tf_dt,
                        dd_tp,
                    ],
                    wrap=True
                ),

                tf_ob,

                lbl_err,

                ft.Row(
                    [
                        btn_salvar,
                        loading_salvar,
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            visible=pode_cadastrar
        )

        self.painel_prazo.content = ft.Column(
            [
                ft.Row(
                    [
                        ft.Text(
                            f"{contrato['nome']} — Prazos",
                            weight=ft.FontWeight.W_600
                        ),

                        ft.Container(
                            padding=ft.padding.symmetric(
                                horizontal=6,
                                vertical=1
                            ),
                            border_radius=4,
                            bgcolor=ft.Colors.BLUE_100,
                            content=ft.Text(
                                f"Identificador: "
                                f"{contrato.get('indice') or '-'}",
                                size=11,
                                color=ft.Colors.BLUE_900,
                            ),
                        ),

                        ft.Container(
                            expand=True
                        ),

                        ft.TextButton(
                            "Verificar informações do contrato",
                            icon=ft.Icons.INFO_OUTLINE,
                            on_click=lambda e:
                                self.app_page.run_task(
                                    ver_contrato_dialog,
                                    self.app_page,
                                    contrato,
                                    self.clientes_map
                                ),
                        ),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),

                prazos_col,

                formulario,

                ft.Text(
                    "Você não tem permissão para cadastrar prazos.",
                    size=12,
                    color=ft.Colors.GREY_500,
                    italic=True,
                    visible=not pode_cadastrar,
                ),

                ft.TextButton(
                    "Fechar",
                    on_click=fechar
                ),
            ]
        )

        self.painel_prazo.visible = True

        self.app_page.update()


def alertas_cadastro_view(page: ft.Page):
    return AlertasCadastroView(page)