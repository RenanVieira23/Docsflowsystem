import flet as ft
from database.models import add_parte, update_parte


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


def _get_tenant_id(page: ft.Page):
    """Obtém o tenant_id salvo na sessão."""
    tenant_id = None

    try:
        if hasattr(page, "local_store") and page.local_store:
            tenant_id = page.local_store.get("tenant_id")
    except Exception:
        pass

    if not tenant_id:
        try:
            tenant_id = page.session.get("tenant_id")
        except Exception:
            pass

    return tenant_id


# ======================================================
# NOVA PARTE
# ======================================================

def nova_parte_dialog(page: ft.Page, on_save):

    tf_nome = ft.TextField(
        label="Nome completo",
        autofocus=True,
        width=380,
    )

    dd_tipo = ft.Dropdown(
        label="Tipo",
        width=380,
        options=[
            ft.dropdown.Option("Física"),
            ft.dropdown.Option("Jurídica"),
        ],
    )

    tf_documento = ft.TextField(
        label="Documento (CPF / CNPJ)",
        width=380,
    )

    def salvar(e):

        if not tf_nome.value or not dd_tipo.value or not tf_documento.value:
            _snack(page, "Preencha todos os campos obrigatórios.")
            return

        tenant_id = _get_tenant_id(page)

        if not tenant_id:
            _snack(page, "Tenant do usuário não encontrado.")
            return

        try:
            resultado = add_parte({
                "nome": tf_nome.value.strip(),
                "tipo": dd_tipo.value,
                "documento": tf_documento.value.strip(),
                "tenant_id": tenant_id,
            })

            if not resultado:
                _snack(page, "Não foi possível cadastrar a parte.")
                return

        except Exception as ex:
            _snack(page, f"Erro ao salvar: {ex}")
            return

        dialog.open = False
        on_save()
        _snack(page, f"Parte '{tf_nome.value}' cadastrada com sucesso.")
        page.update()

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Nova Parte"),
        content=ft.Column(
            [
                tf_nome,
                dd_tipo,
                tf_documento,
            ],
            spacing=10,
            tight=True,
        ),
        actions=[
            ft.TextButton(
                "Cancelar",
                on_click=lambda e: _fechar(dialog, page),
            ),
            ft.FilledButton(
                "Salvar",
                on_click=salvar,
            ),
        ],
        actions_alignment="end",
    )

    return dialog


# ======================================================
# EDITAR PARTE
# ======================================================

def editar_parte_dialog(page: ft.Page, parte: dict, on_save):

    tf_nome = ft.TextField(
        label="Nome completo",
        value=parte.get("nome", ""),
        width=380,
    )

    dd_tipo = ft.Dropdown(
        label="Tipo",
        value=parte.get("tipo"),
        width=380,
        options=[
            ft.dropdown.Option("Física"),
            ft.dropdown.Option("Jurídica"),
        ],
    )

    tf_documento = ft.TextField(
        label="Documento (CPF / CNPJ)",
        value=parte.get("documento", ""),
        width=380,
    )

    def salvar(e):

        if not tf_nome.value or not dd_tipo.value or not tf_documento.value:
            _snack(page, "Preencha todos os campos obrigatórios.")
            return

        tenant_id = _get_tenant_id(page)

        if not tenant_id:
            _snack(page, "Tenant do usuário não encontrado.")
            return

        try:
            resultado = update_parte(
                parte["id"],
                {
                    "nome": tf_nome.value.strip(),
                    "tipo": dd_tipo.value,
                    "documento": tf_documento.value.strip(),
                    "tenant_id": tenant_id,
                },
            )

            if not resultado:
                _snack(page, "Não foi possível atualizar a parte.")
                return

        except Exception as ex:
            _snack(page, f"Erro ao atualizar: {ex}")
            return

        dialog.open = False
        on_save()
        _snack(page, "Parte atualizada com sucesso.")
        page.update()

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Editar Parte"),
        content=ft.Column(
            [
                tf_nome,
                dd_tipo,
                tf_documento,
            ],
            spacing=10,
            tight=True,
        ),
        actions=[
            ft.TextButton(
                "Cancelar",
                on_click=lambda e: _fechar(dialog, page),
            ),
            ft.FilledButton(
                "Salvar alterações",
                on_click=salvar,
            ),
        ],
        actions_alignment="end",
    )

    return dialog