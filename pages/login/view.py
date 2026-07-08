import flet as ft
import asyncio

from database.models import autenticar_usuario
from database.supabase_client import run_db


def login_view(page: ft.Page, navegar):
    """Login compatível com Flet 0.80+ (async correto)"""

    if not hasattr(page, "local_store"):
        page.local_store = {}

    # =========================
    # CAMPOS
    # =========================

    usuario_input = ft.TextField(
        label="Email",
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
    # AUTENTICAR
    # =========================

    async def autenticar(e):

        usuario = usuario_input.value.strip()
        senha = senha_input.value.strip()

        if not usuario or not senha:
            erro_texto.value = "Preencha todos os campos."
            page.update()
            return

        btn_login.disabled = True
        loading.visible = True
        erro_texto.value = ""
        page.update()

        try:
            user = await run_db(
                page,
                autenticar_usuario,
                usuario,
                senha
            )
        except Exception as ex:
            print("Erro login:", ex)
            user = None

        btn_login.disabled = False
        loading.visible = False

        if user:

            print("🔎 USER COMPLETO:", user)
            print("🔎 TENANT ID:", user.get("tenant_id"))
            print("🔎 TENANT NOME:", user.get("tenant_nome"))

    # =========================
    # STORE GLOBAL
    # =========================
            page.local_store["usuario_id"] = user.get("id")
            page.local_store["usuario_nome"] = user.get("usuario", "Usuário")

            tenant_nome = user.get("tenant_nome") or "DocsFlow"

            page.local_store["tenant_id"] = user.get("tenant_id")
            page.local_store["tenant_nome"] = tenant_nome

            page.local_store["is_admin"] = user.get("is_admin", False)
            page.local_store["is_global_admin"] = user.get("is_global_admin", False)

            # =========================
            # 🔥 ATUALIZA LAYOUT (CORRETO)
        # =========================
            if hasattr(page, "layout_instance"):

                layout = page.layout_instance

                layout.set_user(page.local_store["usuario_nome"])
                layout.set_tenant(tenant_nome)

            # =========================
            # SNACKBAR
            # =========================
            page.snack_bar = ft.SnackBar(
                ft.Text(f"Bem-vindo, {page.local_store['usuario_nome']}!")
            )
            page.snack_bar.open = True

            # =========================
            # NAVEGA
            # =========================
            navegar("/dashboard")

        else:
            erro_texto.value = "Usuário ou senha inválidos."

        page.update()
        

    btn_login.on_click = autenticar

    # =========================
    # UI
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
                ft.Image(
                    src="https://mefkcglvxqememduyweh.supabase.co/storage/v1/object/sign/Heringer/LogoDocsFlow2.png?token=eyJraWQiOiJzdG9yYWdlLXVybC1zaWduaW5nLWtleV9jNjM3NDNjNi00NWY4LTRhYWUtODQ0NS05M2EzYmViNjg4OGYiLCJhbGciOiJIUzI1NiJ9.eyJ1cmwiOiJIZXJpbmdlci9Mb2dvRG9jc0Zsb3cyLnBuZyIsImlhdCI6MTc3NjgwMTAwMywiZXhwIjozMzUzNjAxMDAzfQ.5vjzDpm1Zq_XFH9mRvKj5l45AhoMWoc9BGk-B0ALtYM",
                    width=480,
                    height=132,
                    error_content=ft.Text(
                        "DocsFlow",
                        size=20,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.WHITE,
                    ),
                ),

                ft.Divider(),

                usuario_input,
                senha_input,
                erro_texto,

                ft.Row(
                    [btn_login, loading],
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=10,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=20,
        ),
    )

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