import flet as ft
from database.models import criar_usuario_admin, update_usuario_admin


# ======================================================
# HELPERS
# ======================================================

def _snack(page: ft.Page, msg: str):
    page.snack_bar = ft.SnackBar(ft.Text(msg))
    page.snack_bar.open = True
    page.update()


def _fechar(dialog, page):
    dialog.open = False
    page.update()


# ======================================================
# CRIAR USUÁRIO
# ======================================================

def criar_usuario_dialog(page: ft.Page, tenant_id: str, on_save):

    tf_nome = ft.TextField(
        label="Nome do usuário",
        hint_text="Como será exibido no sistema",
        width=380,
        autofocus=True,
    )

    tf_email = ft.TextField(
        label="E-mail",
        hint_text="email@exemplo.com",
        width=380,
        keyboard_type=ft.KeyboardType.EMAIL,
    )

    tf_senha = ft.TextField(
        label="Senha inicial",
        hint_text="Mínimo 6 caracteres",
        width=380,
        password=True,
        can_reveal_password=True,
    )

    tf_senha2 = ft.TextField(
        label="Confirmar senha",
        width=380,
        password=True,
        can_reveal_password=True,
    )

    sw_admin = ft.Switch(
        label="É administrador do tenant",
        value=False,
    )

    lbl_erro = ft.Text(
        "",
        color=ft.Colors.RED_700,
        size=12
    )

    loading = ft.ProgressRing(
        visible=False,
        width=18,
        height=18,
        stroke_width=2
    )

    btn_salvar = ft.FilledButton("Criar usuário")

    def salvar(e):

        lbl_erro.value = ""

        nome = tf_nome.value.strip()
        email = tf_email.value.strip()
        senha = tf_senha.value
        senha2 = tf_senha2.value

        if not nome or not email or not senha:
            lbl_erro.value = "Nome, e-mail e senha são obrigatórios."
            page.update()
            return

        if senha != senha2:
            lbl_erro.value = "As senhas não coincidem."
            page.update()
            return

        if len(senha) < 6:
            lbl_erro.value = "Senha deve ter ao menos 6 caracteres."
            page.update()
            return

        btn_salvar.disabled = True
        loading.visible = True
        page.update()

        resultado = criar_usuario_admin(
            email=email,
            senha=senha,
            nome_usuario=nome,
            tenant_id=tenant_id,
            role="user",                 # sempre usuário
            is_admin=sw_admin.value,     # administrador do tenant
        )

        btn_salvar.disabled = False
        loading.visible = False

        if resultado.get("_error"):
            lbl_erro.value = f"Erro: {resultado['_error']}"
            page.update()
            return

        dialog.open = False
        on_save()
        _snack(page, f"Usuário '{nome}' criado com sucesso.")
        page.update()

    btn_salvar.on_click = salvar

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Novo Usuário"),
        content=ft.Container(
            width=420,
            content=ft.Column(
                [
                    tf_nome,
                    tf_email,
                    tf_senha,
                    tf_senha2,
                    sw_admin,
                    lbl_erro,
                ],
                spacing=12,
                tight=True,
            ),
        ),
        actions=[
            ft.TextButton(
                "Cancelar",
                on_click=lambda e: _fechar(dialog, page)
            ),
            ft.Row(
                [loading, btn_salvar],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
    )

    return dialog


# ======================================================
# EDITAR USUÁRIO
# ======================================================

def editar_usuario_dialog(page: ft.Page, usuario: dict, on_save):

    tf_nome = ft.TextField(
        label="Nome do usuário",
        value=usuario.get("usuario", ""),
        width=380,
    )

    tf_email = ft.TextField(
        label="E-mail",
        value=usuario.get("email", ""),
        width=380,
        disabled=True,   # e-mail é alterado apenas no Auth
    )

    tf_senha = ft.TextField(
        label="Nova senha (deixe em branco para não alterar)",
        width=380,
        password=True,
        can_reveal_password=True,
    )

    sw_admin = ft.Switch(
        label="É administrador do tenant",
        value=bool(usuario.get("is_admin", False)),
    )

    lbl_erro = ft.Text(
        "",
        color=ft.Colors.RED_700,
        size=12
    )

    def salvar(e):

        lbl_erro.value = ""

        nome = tf_nome.value.strip()

        if not nome:
            lbl_erro.value = "Nome é obrigatório."
            page.update()
            return

        dados = {
            "usuario": nome,
            "role": "user",              # sempre usuário
            "is_admin": sw_admin.value,
        }

        if tf_senha.value.strip():

            if len(tf_senha.value.strip()) < 6:
                lbl_erro.value = "Senha deve ter ao menos 6 caracteres."
                page.update()
                return

            dados["senha"] = tf_senha.value.strip()

        resultado = update_usuario_admin(
            usuario["id"],
            dados
        )

        if isinstance(resultado, dict) and resultado.get("_error"):
            lbl_erro.value = f"Erro: {resultado['_error']}"
            page.update()
            return

        dialog.open = False
        on_save()
        _snack(page, f"Usuário '{nome}' atualizado.")
        page.update()

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text(
            f"Editar — {usuario.get('usuario', '')}"
        ),
        content=ft.Container(
            width=420,
            content=ft.Column(
                [
                    tf_nome,
                    tf_email,
                    tf_senha,
                    sw_admin,
                    lbl_erro,
                ],
                spacing=12,
                tight=True,
            ),
        ),
        actions=[
            ft.TextButton(
                "Cancelar",
                on_click=lambda e: _fechar(dialog, page)
            ),
            ft.FilledButton(
                "Salvar alterações",
                on_click=salvar,
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    return dialog