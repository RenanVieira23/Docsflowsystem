import flet as ft


class AppLayout(ft.Column):
    def __init__(self, page: ft.Page, get_view):
        super().__init__(expand=True)

        self.app_page = page
        self.get_view = get_view

        # Cache de views (MUITO importante p/ performance)
        self.views_cache = {}

        # label do usuário
        self.lbl_user = ft.Text("Usuário", size=14)

        # HEADER
        self.header = self._build_header()

        # CONTEÚDO CENTRAL
        self.content_area = ft.Container(
            expand=True,
            padding=24,
            bgcolor=ft.Colors.GREY_50,
        )

        # SIDEBAR
        self.sidebar = self._build_sidebar()

        # LAYOUT PRINCIPAL
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
                ft.PopupMenuItem(
                    content=ft.Text("Perfil"),
                ),
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

    def _build_sidebar(self):

        # botão admin criado antes
        self.btn_admin = self._menu_btn("⚙️ Administração", "/admin")
        return ft.Container(
            width=220,
            bgcolor="#0F2A44",
            padding=20,
            content=ft.Column(
                [
                    ft.Text(
                        "DocsFlow System",
                        size=22,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.WHITE,
                    ),
                    ft.Text(
                        "Gestão Jurídica",
                        size=12,
                        color=ft.Colors.BLUE_100,
                    ),

                    ft.Divider(color=ft.Colors.BLUE_300),

                    self._menu_btn("Dashboard", "/dashboard"),
                    self._menu_btn("Clientes", "/clientes"),
                    self._menu_btn("Tipos de Partes", "/tipos-partes"),
                    self._menu_btn("Partes", "/partes"),
                    self._menu_btn("Contratos", "/contratos"),
                    self._menu_btn("Painel de Alertas", "/alertas"),
                    self._menu_btn("Relatórios", "/relatorios"),

                    # botão admin controlado dinamicamente
                    self.btn_admin,

                        ft.Container(expand=True),
                ],
                spacing=6,
            ),
        )
    # =====================================================
    # BOTÃO MENU (com fundo mais claro no item ativo)
    # =====================================================

    def _build_sidebar(self):

        self.btn_admin = self._menu_btn("⚙️ Administração", "/admin")

        return ft.Container(
            width=220,
            bgcolor="#0F2A44",
            padding=20,
            content=ft.Column(
                controls=[  # ✅ importante no Flet 0.80.x
                    ft.Container(
                        content=ft.Image(
                            src="images/LogoDocsFlow.png",
                            width=160,
                            fit="contain",
                        ),
                        alignment="center",
                        padding=ft.padding.only(bottom=10),
                    ),

                    ft.Divider(color=ft.Colors.BLUE_300),

                    self._menu_btn("Dashboard", "/dashboard"),
                    self._menu_btn("Clientes", "/clientes"),
                    self._menu_btn("Tipos de Partes", "/tipos-partes"),
                    self._menu_btn("Partes", "/partes"),
                    self._menu_btn("Contratos", "/contratos"),
                    self._menu_btn("Painel de Alertas", "/alertas"),
                    self._menu_btn("Relatórios", "/relatorios"),

                    self.btn_admin,

                    ft.Container(expand=True),
                ],
                spacing=6,
            ),
        )
    # =====================================================
    # NAVEGAÇÃO RÁPIDA
    # =====================================================

    def _go_route(self, route):
        # Evita navegação duplicada
        if self.app_page.route == route:
            return

        self.app_page.go(route)

    # =====================================================
    # LOGOUT
    # =====================================================

    def _logout(self, e):
        self.app_page.local_store.clear()

        # Limpa cache ao sair
        self.views_cache.clear()

        self.app_page.go("/login")

    # =====================================================
    # NAVEGAÇÃO PRINCIPAL
    # =====================================================

    def navigate(self, route):

        # =========================
        # DADOS DO USUÁRIO
        # =========================
        nome = self.app_page.local_store.get("usuario_nome", "Usuário")
        self.lbl_user.value = nome

        is_admin = (
            self.app_page.local_store.get("is_admin", False)
            or self.app_page.local_store.get("is_global_admin", False)
        )

        # =========================
        # CONTROLE DE ACESSO REAL
        # =========================
        rotas_admin = ["/admin"]

        if route in rotas_admin and not is_admin:
            self.page.snack_bar = ft.SnackBar(
                ft.Text("Acesso permitido apenas para administradores.")
            )
            self.page.snack_bar.open = True

            route = "/dashboard"   # redireciona

        # =========================
        # CACHE DE VIEW (PERFORMANCE)
        # =========================
        if route in self.views_cache:
            view = self.views_cache[route]
        else:
            view = self.get_view(route)
        self.views_cache[route] = view

        # =========================
        # ATUALIZA CONTEÚDO CENTRAL
        # =========================
        self.content_area.content = view

        # =========================
        # ATUALIZA UI
        # =========================
        self.page.update()

        # Um único update
        self.app_page.update()