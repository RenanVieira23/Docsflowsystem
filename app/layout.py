import flet as ft

from utils.permissoes import pode, eh_administrador, algum_modulo_leitura


class AppLayout(ft.Column):
    def __init__(self, page: ft.Page, get_view):
        super().__init__(expand=True)

        self.app_page = page
        self.get_view = get_view

        # =========================
        # USER LABEL
        # =========================
        self.lbl_user = ft.Text("Usuário", size=14)

        # =========================
        # TENANT LABEL (DINÂMICO)
        # =========================
        self.tenant_text = ft.Text(
            "DocsFlow",
            size=12,
            color=ft.Colors.BLUE_100,
        )

        # =========================
        # HEADER
        # =========================
        self.header = self._build_header()

        # =========================
        # CONTEÚDO CENTRAL
        # =========================
        self.content_area = ft.Container(
            expand=True,
            padding=24,
            bgcolor=ft.Colors.GREY_50,
        )

        # =========================
        # SIDEBAR
        # =========================
        # FIX: o sidebar é montado antes do login acontecer (quando
        # page.local_store ainda está vazio), então as checagens de
        # permissão abaixo ficariam todas "false" pra sempre e o menu
        # apareceria vazio até um F5. Por isso o sidebar mora dentro
        # de um Container cujo .content é RECONSTRUÍDO a cada
        # navigate() (ver _refresh_sidebar), já com as permissões da
        # sessão atual.
        self.sidebar = ft.Container(width=220, bgcolor="#0F2A44", padding=20)
        self._refresh_sidebar()

        # =========================
        # LAYOUT PRINCIPAL
        # =========================
        self.controls = [
            ft.Row(
                [
                    self.sidebar,
                    ft.Column(
                        [
                            self.header,
                            self.content_area,
                        ],
                        expand=True,
                    ),
                ],
                expand=True,
            )
        ]

    # =====================================================
    # HEADER
    # =====================================================

    def _build_header(self):
        self.menu_user = ft.PopupMenuButton(
            content=ft.Row(
                [
                    ft.CircleAvatar(
                        content=ft.Text("U"),
                        bgcolor=ft.Colors.BLUE_600,
                        color=ft.Colors.WHITE,
                        radius=16,
                    ),
                    self.lbl_user,
                    ft.Icon(ft.Icons.ARROW_DROP_DOWN),
                ],
                spacing=6,
            ),
            items=[
                ft.PopupMenuItem(content=ft.Text("Perfil")),
                ft.PopupMenuItem(
                    content=ft.Text("Sair"),
                    on_click=self._logout,
                ),
            ],
        )

        return ft.Container(
            height=56,
            bgcolor=ft.Colors.WHITE,
            padding=ft.padding.symmetric(horizontal=24),
            border=ft.border.only(
                bottom=ft.BorderSide(1, ft.Colors.GREY_200)
            ),
            content=ft.Row(
                [
                    ft.Text(
                        "Painel",
                        size=16,
                        weight=ft.FontWeight.W_600,
                    ),
                    ft.Container(expand=True),
                    self.menu_user,
                ],
            ),
        )

    # =====================================================
    # SIDEBAR
    # =====================================================

    def _refresh_sidebar(self):
        """Reconstrói o conteúdo do sidebar com as permissões atuais
        da sessão. Chamado no __init__ e a cada navigate()."""
        self.sidebar.content = self._build_sidebar_content()

    def _build_sidebar_content(self):

        self.btn_admin = self._menu_btn("⚙️ Administração", "/admin")
        self.btn_cargos = self._menu_btn("🔐 Cargos e Permissões", "/cargos")

        itens_menu = []

        itens_menu.append(self._menu_btn("Dashboard", "/dashboard"))

        if pode(self.app_page, "clientes", "ler"):
            itens_menu.append(self._menu_btn("Clientes", "/clientes"))

        if pode(self.app_page, "categorias", "ler"):
            itens_menu.append(self._menu_btn("Categorias", "/tipos-partes"))

        if pode(self.app_page, "partes", "ler"):
            itens_menu.append(self._menu_btn("Partes", "/partes"))

        if pode(self.app_page, "contratos", "ler"):
            itens_menu.append(self._menu_btn("Contratos", "/contratos"))

        if pode(self.app_page, "prazos", "ler"):
            itens_menu.append(self._menu_btn("Painel de Alertas", "/alertas"))
            itens_menu.append(self._menu_btn("Cadastro de Prazos", "/alertas-cadastro"))

        if algum_modulo_leitura(self.app_page):
            itens_menu.append(self._menu_btn("Relatórios", "/relatorios"))

        if eh_administrador(self.app_page):
            itens_menu.append(self.btn_admin)
            itens_menu.append(self.btn_cargos)

        return ft.Column(
            [
                ft.Image(
                    src="https://mefkcglvxqememduyweh.supabase.co/storage/v1/object/sign/Heringer/LogoDocsFlow2-removebg-preview.png?token=eyJraWQiOiJzdG9yYWdlLXVybC1zaWduaW5nLWtleV9jNjM3NDNjNi00NWY4LTRhYWUtODQ0NS05M2EzYmViNjg4OGYiLCJhbGciOiJIUzI1NiJ9.eyJ1cmwiOiJIZXJpbmdlci9Mb2dvRG9jc0Zsb3cyLXJlbW92ZWJnLXByZXZpZXcucG5nIiwiaWF0IjoxNzc2ODAxMTI1LCJleHAiOjMzNTM2MDExMjV9.jqxPmg6Nmp6XfSppw6NUzjhnyINV0dw-x_Gv3ejjftg",
                    width=160,
                    height=44,
                    error_content=ft.Text(
                        "DocsFlow",
                        size=20,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.WHITE,
                    ),
                ),

                # =========================
                # TENANT DINÂMICO
                # =========================
                self.tenant_text,

                ft.Divider(color=ft.Colors.BLUE_300),

                *itens_menu,

                ft.Container(expand=True),
            ],
            spacing=6,
        )

    # =====================================================
    # BOTÃO MENU
    # =====================================================

    def _menu_btn(self, text, route):
        is_active = (self.app_page.route == route)

        return ft.Container(
            border_radius=8,
            bgcolor="#1B3E63" if is_active else "#0F2A44",
            padding=ft.padding.symmetric(vertical=10, horizontal=12),
            content=ft.Text(
                text,
                color=ft.Colors.WHITE,
                size=14,
                weight=ft.FontWeight.W_600 if is_active else ft.FontWeight.W_500,
            ),
            ink=True,
            on_click=lambda e, r=route: self._go_route(r),
        )

    # =====================================================
    # NAVEGAÇÃO
    # =====================================================

    def _go_route(self, route):
        if self.app_page.route == route:
            return
        self.app_page.go(route)

    # =====================================================
    # LOGOUT
    # =====================================================

    def _logout(self, e):
        # FIX: local_store.clear() também apagava "supabase_client" — e
        # como main() só roda de novo com um F5 completo no navegador
        # (não a cada logout/login dentro da mesma sessão), o sistema
        # ficava sem client nenhum guardado. O próximo login então usava
        # um client "de socorro" descartável a cada chamada (nunca salvo
        # de volta), e por isso nada mais carregava direito até dar F5
        # manualmente. Agora recriamos um client novo e limpo aqui,
        # pronto pro próximo login.
        from database.supabase_client import new_session_client
        from utils.log_acao import log_acao

        log_acao(self.app_page, "Logout realizado")

        self.app_page.local_store.clear()
        self.app_page.local_store["supabase_client"] = new_session_client()
        self.app_page.go("/login")

    # =====================================================
    # ATUALIZAÇÕES DINÂMICAS (ESSENCIAL)
    # =====================================================

    def set_user(self, name: str):
        self.lbl_user.value = name
        self.app_page.update()

    def set_tenant(self, tenant_name: str):
        self.tenant_text.value = tenant_name
        self.app_page.update()

    # =====================================================
    # NAVEGAÇÃO PRINCIPAL
    # =====================================================

    def navigate(self, route):

        self.lbl_user.value = self.app_page.local_store.get("usuario_nome", "Usuário")

        # FIX: o sidebar era montado uma única vez, antes do login (com
        # page.local_store vazio) — as permissões nunca eram reavaliadas
        # depois, então o menu ficava vazio até um F5. Agora ele é
        # reconstruído a cada navegação, já refletindo o cargo/
        # permissões da sessão atual.
        self._refresh_sidebar()

        is_admin = eh_administrador(self.app_page)

        if route in ("/admin", "/cargos") and not is_admin:
            self.app_page.snack_bar = ft.SnackBar(
                ft.Text("Acesso permitido apenas para administradores.")
            )
            self.app_page.snack_bar.open = True
            route = "/dashboard"

        # FIX: antes, a view de cada rota era guardada aqui e nunca mais
        # reconstruída na mesma sessão — por isso dados criados em outra
        # tela (ex: um novo contrato) só apareciam na PRIMEIRA vez que a
        # tela era visitada. Agora cada navegação chama get_view() de
        # novo, sempre com dados atuais.
        view = self.get_view(route)

        self.content_area.content = view
        self.app_page.update()