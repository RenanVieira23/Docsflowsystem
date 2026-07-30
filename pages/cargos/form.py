import flet as ft
from database.models import criar_usuario_admin, update_usuario_admin, get_cargos
from database.supabase_client import run_db
from utils.log_acao import log_acao


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


def _carregar_cargos_no_dropdown(page: ft.Page, tenant_id: str, dd_cargo: ft.Dropdown, valor_inicial=None):
    """
    Popula o dropdown de cargo de forma assíncrona, sem exigir que a
    função que abre o diálogo (criar_usuario_dialog/editar_usuario_dialog)
    vire async — o diálogo já abre na hora, com "Carregando..." no
    dropdown, e as opções aparecem assim que a busca terminar.
    """
    async def _carregar():
        try:
            cargos = await run_db(page, get_cargos, tenant_id) or []
        except Exception as ex:
            print("❌ Erro ao carregar cargos:", ex)
            cargos = []

        if not cargos:
            dd_cargo.hint_text = "Nenhum cargo cadastrado — crie um em Cargos e Permissões"
            dd_cargo.options = []
        else:
            dd_cargo.options = [ft.dropdown.Option(str(c["id"]), c["nome"]) for c in cargos]
            if valor_inicial and any(str(c["id"]) == str(valor_inicial) for c in cargos):
                dd_cargo.value = str(valor_inicial)
            elif not dd_cargo.value:
                # sugere "Executor" como padrão para usuário novo; se não
                # existir, deixa em branco mesmo (obrigatório escolher)
                executor = next((c for c in cargos if c["nome"] == "Executor"), None)
                if executor:
                    dd_cargo.value = str(executor["id"])

        try:
            dd_cargo.update()
        except Exception:
            pass

    page.run_task(_carregar)


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

    dd_cargo = ft.Dropdown(
        label="Cargo",
        hint_text="Carregando cargos...",
        width=380,
        options=[],
    )
    _carregar_cargos_no_dropdown(page, tenant_id, dd_cargo)

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

    async def salvar(e):

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

        if not dd_cargo.value:
            lbl_erro.value = "Selecione um cargo para o usuário."
            page.update()
            return

        btn_salvar.disabled = True
        loading.visible = True
        page.update()

        try:
            # "Administrador" também liga a flag legada is_admin, usada
            # em outras partes do sistema para checagens rápidas de acesso.
            cargo_escolhido = next(
                (o for o in dd_cargo.options if o.key == dd_cargo.value), None
            )
            eh_admin = bool(cargo_escolhido and cargo_escolhido.text == "Administrador")

            resultado = await run_db(
                page, criar_usuario_admin,
                email=email,
                senha=senha,
                nome_usuario=nome,
                tenant_id=tenant_id,
                role="user",
                is_admin=eh_admin,
                cargo_id=int(dd_cargo.value),
            )
        except Exception as ex:
            btn_salvar.disabled = False
            loading.visible = False
            lbl_erro.value = f"Erro de conexão: {ex}"
            page.update()
            return

        btn_salvar.disabled = False
        loading.visible = False

        if resultado.get("_error"):
            lbl_erro.value = f"Erro: {resultado['_error']}"
            page.update()
            return

        dialog.open = False
        on_save()
        _snack(page, f"Usuário '{nome}' criado com sucesso.")
        log_acao(page, f"Usuário criado: '{nome}'", f"email={email} cargo_id={dd_cargo.value}")
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
                    dd_cargo,
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

    dd_cargo = ft.Dropdown(
        label="Cargo",
        hint_text="Carregando cargos...",
        width=380,
        options=[],
    )
    _carregar_cargos_no_dropdown(
        page, usuario.get("tenant_id"), dd_cargo, valor_inicial=usuario.get("cargo_id")
    )

    lbl_erro = ft.Text(
        "",
        color=ft.Colors.RED_700,
        size=12
    )

    async def salvar(e):

        lbl_erro.value = ""

        nome = tf_nome.value.strip()

        if not nome:
            lbl_erro.value = "Nome é obrigatório."
            page.update()
            return

        if not dd_cargo.value:
            lbl_erro.value = "Selecione um cargo para o usuário."
            page.update()
            return

        cargo_escolhido = next(
            (o for o in dd_cargo.options if o.key == dd_cargo.value), None
        )
        eh_admin = bool(cargo_escolhido and cargo_escolhido.text == "Administrador")

        dados = {
            "usuario": nome,
            "role": "user",
            "is_admin": eh_admin,
            "cargo_id": int(dd_cargo.value),
        }

        if tf_senha.value.strip():

            if len(tf_senha.value.strip()) < 6:
                lbl_erro.value = "Senha deve ter ao menos 6 caracteres."
                page.update()
                return

            dados["senha"] = tf_senha.value.strip()

        try:
            resultado = await run_db(page, update_usuario_admin, usuario["id"], dados)
        except Exception as ex:
            lbl_erro.value = f"Erro de conexão: {ex}"
            page.update()
            return

        if isinstance(resultado, dict) and resultado.get("_error"):
            lbl_erro.value = f"Erro: {resultado['_error']}"
            page.update()
            return

        dialog.open = False
        on_save()
        _snack(page, f"Usuário '{nome}' atualizado.")
        log_acao(page, f"Usuário editado: '{nome}'", f"usuario_id={usuario['id']} cargo_id={dd_cargo.value}")
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
                    dd_cargo,
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