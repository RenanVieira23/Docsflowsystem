import flet as ft
import asyncio

from database.models import autenticar_usuario


def login_view(page: ft.Page, navegar):
    """Login compatível com Flet 0.80+ (async correto)"""

    # Garante storage
    if not hasattr(page, "local_store"):
        page.local_store = {}


    # =========================
    # CAMPOS
    # =========================

    usuario_input = ft.TextField(
        label="Usuário",
        width=300,
        border_radius=8,
        autofocus=True,
    )

    senha_input = ft.TextField(
        label="Senha",
        width=300,
        password=True,
        can_reveal_password=True,
        border_radius=8,
    )

    erro_texto = ft.Text(
        "",
        color=ft.Colors.RED_700,
        size=12,
        text_align=ft.TextAlign.CENTER,
    )


    # =========================
    # LOADING
    # =========================

    loading = ft.ProgressRing(
        visible=False,
        width=22,
        height=22,
        stroke_width=2,
    )

    btn_login = ft.ElevatedButton(
        "Entrar",
        width=300,
        bgcolor=ft.Colors.BLUE_700,
        color=ft.Colors.WHITE,
    )


    # =========================
    # AUTENTICAR (ASYNC REAL)
    # =========================

    async def autenticar(e):

        usuario = usuario_input.value.strip()
        senha = senha_input.value.strip()


        if not usuario or not senha:

            erro_texto.value = "Preencha todos os campos."
            page.update()
            return


        # Bloqueia botão
        btn_login.disabled = True
        loading.visible = True
        erro_texto.value = ""

        page.update()


        try:

            # Roda fora da UI e PEGA retorno
            user = await asyncio.to_thread(
                autenticar_usuario,
                usuario,
                senha
            )

        except Exception as ex:

            print("Erro login:", ex)
            user = None


        # Libera botão
        btn_login.disabled = False
        loading.visible = False


        if user:

            page.local_store["usuario_id"]       = user.get("id")
            page.local_store["usuario_nome"]      = user.get("usuario", "Usuário")
            page.local_store["tenant_id"]         = user.get("tenant_id")
            page.local_store["is_admin"]          = user.get("is_admin", False)
            page.local_store["is_global_admin"]   = user.get("is_global_admin", False)

            page.snack_bar = ft.SnackBar(
                ft.Text(f"Bem-vindo, {page.local_store['usuario_nome']}!")
            )

            page.snack_bar.open = True

            navegar("/dashboard")

        else:

            erro_texto.value = "Usuário ou senha inválidos."


        page.update()


    btn_login.on_click = autenticar


    # =========================
    # CARD
    # =========================

    card_login = ft.Container(
        width=380,
        padding=40,
        bgcolor=ft.Colors.WHITE,
        border_radius=12,

        shadow=ft.BoxShadow(
            blur_radius=12,
            color=ft.Colors.BLUE_GREY_100
        ),

        content=ft.Column(
            [
                ft.Container(
                    content=ft.Image(
                        src="images/LogoDocsFlow2.png",
                        width=220,
                        fit="contain",
                    ),
                    alignment="center",
                ),

                ft.Text(
                    "Acesse com suas credenciais",
                    size=14,
                    color=ft.Colors.GREY_700,
                ),

                ft.Divider(),

                usuario_input,

                senha_input,

                erro_texto,

                ft.Row(
                    [
                        btn_login,
                        loading,
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=10,
                ),
            ],

            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=20,
        ),
    )


    # =========================
    # LAYOUT
    # =========================

    layout = ft.Container(
        expand=True,
        bgcolor=ft.Colors.BLUE_50,

        content=ft.Row(
            [
                ft.Container(expand=True),

                ft.Column(
                    [
                        card_login,

                        ft.Text(
                            "Desenvolvido por @renanv.dev",
                            size=12,
                            color=ft.Colors.GREY_600,
                        ),
                    ],

                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    expand=True,
                ),

                ft.Container(expand=True),
            ],

            alignment=ft.MainAxisAlignment.CENTER,
        ),

        alignment=ft.Alignment(0, 0),
    )


    return layout