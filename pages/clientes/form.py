import flet as ft

from utils.sigla import gerar_sigla
from database.models import add_cliente, update_cliente


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
# NOVO CLIENTE
# ======================================================

def novo_cliente_dialog(page: ft.Page, atualizar_tabela):

    tf_nome = ft.TextField(label="Nome do Cliente", autofocus=True)
    dd_tipo = ft.Dropdown(
        label="Tipo",
        options=[
            ft.dropdown.Option("Física"),
            ft.dropdown.Option("Jurídica"),
        ],
    )

    tf_documento = ft.TextField(label="Documento (CPF / CNPJ)")

    # -------------------------
    # SALVAR
    # -------------------------
    def salvar(e):

        if not tf_nome.value or not dd_tipo.value or not tf_documento.value:
            _snack(page, "Preencha todos os campos obrigatórios.")
            return

        sigla_auto = gerar_sigla(tf_nome.value)

        try:
            add_cliente(
                {
                    "nome": tf_nome.value,
                    "tipo": dd_tipo.value,
                    "documento": tf_documento.value,
                    "sigla": sigla_auto,
                    "tenant_id": page.local_store["tenant_id"]
                }
            )

        except Exception as ex:
            _snack(page, f"Erro ao salvar cliente: {ex}")
            return

        dialog.open = False
        atualizar_tabela()

        _snack(page, f"Cliente '{tf_nome.value}' cadastrado com sucesso.")

        page.update()

    # -------------------------
    # DIALOG
    # -------------------------
    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Novo Cliente"),

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
# EDITAR CLIENTE
# ======================================================

def editar_cliente_dialog(
    page: ft.Page,
    cliente: dict,
    on_save,
):

    tf_nome = ft.TextField(
        label="Nome do Cliente",
        value=cliente.get("nome", ""),
    )

    dd_tipo = ft.Dropdown(
        label="Tipo",
        value=cliente.get("tipo"),
        options=[
            ft.dropdown.Option("Física"),
            ft.dropdown.Option("Jurídica"),
        ],
    )

    tf_documento = ft.TextField(
        label="Documento (CPF / CNPJ)",
        value=cliente.get("documento", ""),
    )

    tf_sigla = ft.TextField(
        label="Sigla",
        value=cliente.get("sigla", ""),
        disabled=True,
    )

    # -------------------------
    # SALVAR
    # -------------------------
    def salvar(e):

        if not tf_nome.value or not dd_tipo.value or not tf_documento.value:
            _snack(page, "Preencha todos os campos obrigatórios.")
            return

        try:
            update_cliente(
                cliente["id"],
                {
                    "nome": tf_nome.value,
                    "tipo": dd_tipo.value,
                    "documento": tf_documento.value,
                },
            )

        except Exception as ex:
            _snack(page, f"Erro ao atualizar cliente: {ex}")
            return

        dialog.open = False

        on_save()

        _snack(page, "Cliente atualizado com sucesso.")

        page.update()

    # -------------------------
    # DIALOG
    # -------------------------
    dialog = ft.AlertDialog(
        modal=True,

        title=ft.Text("Editar Cliente"),

        content=ft.Column(
            [
                tf_nome,
                dd_tipo,
                tf_documento,
                tf_sigla,
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


# ======================================================
# VER CLIENTE
# ======================================================

def ver_cliente_dialog(
    page: ft.Page,
    cliente: dict,
):

    dialog = ft.AlertDialog(
        modal=True,

        title=ft.Text("Dados do Cliente"),

        content=ft.Column(
            [
                ft.Text(f"Nome: {cliente.get('nome', '')}"),
                ft.Text(f"Tipo: {cliente.get('tipo', '')}"),
                ft.Text(f"Documento: {cliente.get('documento', '')}"),
                ft.Text(f"Sigla: {cliente.get('sigla', '')}"),
            ],
            spacing=8,
        ),

        actions=[
            ft.TextButton(
                "Fechar",
                on_click=lambda e: _fechar(dialog, page),
            )
        ],
    )

    page.overlay.append(dialog)

    dialog.open = True

    page.update()
