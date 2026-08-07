import flet as ft
import asyncio

from database.models import (
    autenticar_usuario,
    solicitar_redefinicao_senha,
    confirmar_redefinicao_senha,
    registrar_aceite_termos,
)
from database.supabase_client import run_db
from pages.termos.view import dialog_termos
from utils.termos import precisa_aceitar_termos, VERSAO_TERMOS_ATUAL


def login_view(page: ft.Page, navegar):
    """Login compatível com Flet 0.80+ (async correto), com fluxo de
    recuperação de senha por código numérico e gate obrigatório de
    aceite dos Termos de Uso / Política de Privacidade (LGPD)."""

    if not hasattr(page, "local_store"):
        page.local_store = {}

    # =========================
    # ESTADO DA TELA
    # =========================
    # "login" | "recuperar_email" | "recuperar_codigo"
    estado = {"tela": "login", "email_recuperacao": "", "usuario_pendente": None}

    # =========================
    # CAMPOS — LOGIN
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

    btn_esqueci = ft.TextButton(
        "Esqueci minha senha",
        on_click=lambda e: mostrar("recuperar_email"),
    )

    btn_ver_termos = ft.TextButton(
        "Termos de Uso e Política de Privacidade",
        on_click=lambda e: dialog_termos(page, modo="leitura"),
    )

    # =========================
    # CAMPOS — RECUPERAR (ETAPA 1: informar e-mail)
    # =========================

    rec_email_input = ft.TextField(
        label="Email cadastrado",
        width=300,
        border_radius=8,
    )

    rec_email_erro = ft.Text("", color=ft.Colors.RED_700, size=12, text_align=ft.TextAlign.CENTER)
    rec_email_loading = ft.ProgressRing(visible=False, width=22, height=22, stroke_width=2)

    btn_enviar_codigo = ft.ElevatedButton(
        "Enviar código",
        width=300,
        bgcolor=ft.Colors.BLUE_700,
        color=ft.Colors.WHITE,
    )

    btn_voltar_login_1 = ft.TextButton(
        "Voltar para o login",
        on_click=lambda e: mostrar("login"),
    )

    # =========================
    # CAMPOS — RECUPERAR (ETAPA 2: código + nova senha)
    # =========================

    rec_codigo_input = ft.TextField(
        label="Código recebido por e-mail",
        width=300,
        border_radius=8,
        max_length=20,
        keyboard_type=ft.KeyboardType.NUMBER,
    )

    rec_nova_senha_input = ft.TextField(
        label="Nova senha",
        width=300,
        password=True,
        can_reveal_password=True,
        border_radius=8,
    )

    rec_confirmar_senha_input = ft.TextField(
        label="Confirmar nova senha",
        width=300,
        password=True,
        can_reveal_password=True,
        border_radius=8,
    )

    rec_codigo_erro = ft.Text("", color=ft.Colors.RED_700, size=12, text_align=ft.TextAlign.CENTER)
    rec_codigo_loading = ft.ProgressRing(visible=False, width=22, height=22, stroke_width=2)
    rec_email_label = ft.Text("", size=12, color=ft.Colors.GREY_600, text_align=ft.TextAlign.CENTER)

    btn_confirmar_nova_senha = ft.ElevatedButton(
        "Redefinir senha",
        width=300,
        bgcolor=ft.Colors.BLUE_700,
        color=ft.Colors.WHITE,
    )

    btn_reenviar_codigo = ft.TextButton("Reenviar código")
    btn_voltar_login_2 = ft.TextButton(
        "Voltar para o login",
        on_click=lambda e: mostrar("login"),
    )

    # =========================
    # FINALIZAÇÃO DO LOGIN (compartilhada entre fluxo direto e
    # fluxo que passa pelo gate de aceite de termos)
    # =========================

    async def _concluir_login(user: dict):
        page.local_store["usuario_id"] = user.get("id")
        page.local_store["usuario_nome"] = user.get("usuario", "Usuário")

        tenant_nome = user.get("tenant_nome") or "DocsFlow"

        page.local_store["tenant_id"] = user.get("tenant_id")
        page.local_store["tenant_nome"] = tenant_nome

        page.local_store["is_admin"] = user.get("is_admin", False)
        page.local_store["is_global_admin"] = user.get("is_global_admin", False)

        # Cargo + permissões por módulo (ver database/models.py ->
        # autenticar_usuario / get_permissoes_usuario). Guardado uma
        # vez aqui e lido em toda checagem via utils/permissoes.py.
        page.local_store["cargo_id"] = user.get("cargo_id")
        page.local_store["cargo_nome"] = user.get("cargo_nome")
        page.local_store["permissoes"] = user.get("permissoes", {})

        # =========================
        # SESSÃO (access/refresh token)
        # =========================
        # Necessário para a renovação automática de token em
        # database/supabase_client.py (_garantir_sessao_valida).
        sessao = user.get("_session") or {}
        page.local_store["session_access_token"] = sessao.get("access_token")
        page.local_store["session_refresh_token"] = sessao.get("refresh_token")
        page.local_store["session_expires_at"] = sessao.get("expires_at")

        # =========================
        # 🔥 ATUALIZA LAYOUT
        # =========================
        if hasattr(page, "layout_instance"):
            layout = page.layout_instance
            layout.set_user(page.local_store["usuario_nome"])
            layout.set_tenant(tenant_nome)

        # =========================
        # LOG
        # =========================
        from utils.log_acao import log_acao
        log_acao(page, "Login realizado", f"usuario={user.get('email') or user.get('usuario')}")

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
        page.update()

    # =========================
    # GATE DE TERMOS (LGPD)
    # =========================

    async def _on_aceitar_termos():
        user = estado.get("usuario_pendente")
        if not user:
            return

        try:
            resultado = await run_db(page, registrar_aceite_termos, user["id"], VERSAO_TERMOS_ATUAL)
        except Exception as ex:
            print("Erro ao registrar aceite dos termos:", ex)
            resultado = {"_error": "Erro de conexão."}

        if isinstance(resultado, dict) and resultado.get("_error"):
            erro_texto.value = (
                "Não foi possível registrar seu aceite dos termos. "
                "Tente fazer login novamente."
            )
            estado["usuario_pendente"] = None
            page.update()
            return

        estado["usuario_pendente"] = None
        await _concluir_login(user)

    async def _on_recusar_termos():
        # Encerra a sessão de autenticação já criada e limpa qualquer
        # estado parcial — o uso do Sistema não é liberado sem aceite.
        try:
            await run_db(page, lambda: __import__("database.supabase_client", fromlist=["supabase"]).supabase.auth.sign_out())
        except Exception:
            pass

        estado["usuario_pendente"] = None
        page.local_store.clear()

        erro_texto.value = "É necessário aceitar os Termos de Uso e a Política de Privacidade para utilizar o Sistema."
        page.update()

    def _mostrar_gate_termos(user: dict):
        estado["usuario_pendente"] = user
        dialog_termos(
            page,
            modo="aceite",
            on_aceitar=_on_aceitar_termos,
            on_recusar=_on_recusar_termos,
        )

    # =========================
    # AUTENTICAR (LOGIN)
    # =========================

    async def autenticar(e):

        usuario = (usuario_input.value or "").strip()
        senha = (senha_input.value or "").strip()

        if not usuario or not senha:
            erro_texto.value = "Preencha todos os campos."
            page.update()
            return

        btn_login.disabled = True
        loading.visible = True
        erro_texto.value = ""
        page.update()

        try:
            user = await run_db(page, autenticar_usuario, usuario, senha)
        except Exception as ex:
            print("Erro login:", ex)
            user = None

        btn_login.disabled = False
        loading.visible = False

        # Erro tratado (bloqueio por tentativas, perfil não encontrado, etc.)
        if isinstance(user, dict) and user.get("_error"):
            if user["_error"] == "PERFIL_NAO_ENCONTRADO":
                erro_texto.value = "Perfil de usuário não encontrado. Contate o administrador."
            else:
                erro_texto.value = user["_error"]
            page.update()
            return

        if user:
            if precisa_aceitar_termos(user):
                loading.visible = False
                page.update()
                _mostrar_gate_termos(user)
                return

            await _concluir_login(user)

        else:
            erro_texto.value = "Usuário ou senha inválidos."
            page.update()

    btn_login.on_click = autenticar

    # =========================
    # RECUPERAR — ENVIO DO CÓDIGO (compartilhado entre etapa 1 e "reenviar")
    # =========================

    async def _enviar_codigo_para(email: str) -> dict:
        try:
            return await run_db(page, solicitar_redefinicao_senha, email)
        except Exception as ex:
            print("Erro ao solicitar redefinição:", ex)
            return {"_error": "Erro de conexão. Tente novamente."}

    async def enviar_codigo(e=None):
        email = (rec_email_input.value or "").strip()

        rec_email_erro.value = ""

        if not email or "@" not in email:
            rec_email_erro.value = "Informe um e-mail válido."
            page.update()
            return

        btn_enviar_codigo.disabled = True
        rec_email_loading.visible = True
        page.update()

        resultado = await _enviar_codigo_para(email)

        btn_enviar_codigo.disabled = False
        rec_email_loading.visible = False

        if isinstance(resultado, dict) and resultado.get("_error"):
            rec_email_erro.value = resultado["_error"]
            page.update()
            return

        estado["email_recuperacao"] = email
        rec_email_input.value = ""
        mostrar("recuperar_codigo")

    btn_enviar_codigo.on_click = lambda e: page.run_task(enviar_codigo)

    async def reenviar_codigo(e=None):
        email = estado.get("email_recuperacao", "")
        if not email:
            return

        rec_codigo_erro.color = ft.Colors.RED_700
        resultado = await _enviar_codigo_para(email)

        if isinstance(resultado, dict) and resultado.get("_error"):
            rec_codigo_erro.value = resultado["_error"]
        else:
            rec_codigo_erro.color = ft.Colors.GREEN_700
            rec_codigo_erro.value = "Código reenviado. Confira seu e-mail."

        page.update()

    btn_reenviar_codigo.on_click = lambda e: page.run_task(reenviar_codigo)

    # =========================
    # RECUPERAR — ETAPA 2: confirmar código + nova senha
    # =========================

    async def confirmar_nova_senha(e):
        codigo = (rec_codigo_input.value or "").strip()
        nova = (rec_nova_senha_input.value or "").strip()
        confirmar = (rec_confirmar_senha_input.value or "").strip()

        rec_codigo_erro.color = ft.Colors.RED_700
        rec_codigo_erro.value = ""

        if not codigo or not nova or not confirmar:
            rec_codigo_erro.value = "Preencha todos os campos."
            page.update()
            return

        if nova != confirmar:
            rec_codigo_erro.value = "As senhas não coincidem."
            page.update()
            return

        if len(nova) < 6:
            rec_codigo_erro.value = "A senha deve ter ao menos 6 caracteres."
            page.update()
            return

        btn_confirmar_nova_senha.disabled = True
        rec_codigo_loading.visible = True
        page.update()

        try:
            resultado = await run_db(
                page, confirmar_redefinicao_senha,
                estado["email_recuperacao"], codigo, nova,
            )
        except Exception as ex:
            print("Erro ao confirmar redefinição:", ex)
            resultado = {"_error": "Erro de conexão. Tente novamente."}

        btn_confirmar_nova_senha.disabled = False
        rec_codigo_loading.visible = False

        if isinstance(resultado, dict) and resultado.get("_error"):
            rec_codigo_erro.value = resultado["_error"]
            page.update()
            return

        rec_codigo_input.value = ""
        rec_nova_senha_input.value = ""
        rec_confirmar_senha_input.value = ""
        estado["email_recuperacao"] = ""

        page.snack_bar = ft.SnackBar(
            ft.Text("Senha redefinida com sucesso! Faça login com a nova senha.")
        )
        page.snack_bar.open = True

        mostrar("login")

    btn_confirmar_nova_senha.on_click = confirmar_nova_senha

    # =========================
    # ÁREA DINÂMICA (troca de tela dentro do mesmo card)
    # =========================

    form_area = ft.Column(spacing=16, horizontal_alignment=ft.CrossAxisAlignment.CENTER)

    def _tela_login():
        return [
            usuario_input,
            senha_input,
            erro_texto,
            ft.Row([btn_login, loading], alignment=ft.MainAxisAlignment.CENTER, spacing=10),
            btn_esqueci,
            ft.Divider(height=1),
            btn_ver_termos,
        ]

    def _tela_recuperar_email():
        rec_email_erro.value = ""
        return [
            ft.Text(
                "Informe o e-mail cadastrado. Se ele existir no sistema, "
                "enviaremos um código de verificação.",
                size=12, color=ft.Colors.GREY_600, text_align=ft.TextAlign.CENTER,
            ),
            rec_email_input,
            rec_email_erro,
            ft.Row(
                [btn_enviar_codigo, rec_email_loading],
                alignment=ft.MainAxisAlignment.CENTER, spacing=10,
            ),
            btn_voltar_login_1,
        ]

    def _tela_recuperar_codigo():
        rec_codigo_erro.value = ""
        rec_codigo_erro.color = ft.Colors.RED_700
        rec_email_label.value = f"Código enviado para: {estado['email_recuperacao']}"
        return [
            rec_email_label,
            rec_codigo_input,
            rec_nova_senha_input,
            rec_confirmar_senha_input,
            rec_codigo_erro,
            ft.Row(
                [btn_confirmar_nova_senha, rec_codigo_loading],
                alignment=ft.MainAxisAlignment.CENTER, spacing=10,
            ),
            ft.Row([btn_reenviar_codigo, btn_voltar_login_2], alignment=ft.MainAxisAlignment.CENTER, wrap=True),
        ]

    def mostrar(tela: str):
        estado["tela"] = tela
        if tela == "login":
            erro_texto.value = ""
            form_area.controls = _tela_login()
        elif tela == "recuperar_email":
            form_area.controls = _tela_recuperar_email()
        elif tela == "recuperar_codigo":
            form_area.controls = _tela_recuperar_codigo()
        page.update()

    mostrar("login")

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

                form_area,
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