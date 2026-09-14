import flet as ft

from utils.sigla import gerar_sigla
from database.models import add_cliente, update_cliente
from database.supabase_client import run_db
from utils.erros_ui import snack_erro, snack_sucesso
from utils.log_acao import log_acao


# ======================================================
# HELPERS
# ======================================================

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

    lbl_erro = ft.Text("", color=ft.Colors.RED_700, size=12)

    # -------------------------
    # SALVAR
    # -------------------------
    async def salvar(e):

        lbl_erro.value = ""

        if not tf_nome.value or not dd_tipo.value or not tf_documento.value:
            lbl_erro.value = "Preencha todos os campos obrigatórios."
            page.update()
            return

        sigla_auto = gerar_sigla(tf_nome.value)

        try:
            resultado = await run_db(
                page,
                add_cliente,
                {
                    "nome": tf_nome.value,
                    "tipo": dd_tipo.value,
                    "documento": tf_documento.value,
                    "sigla": sigla_auto,
                    "tenant_id": page.local_store["tenant_id"]
                }
            )

        except Exception as ex:
            snack_erro(page, ex, contexto="salvar o cliente")
            return

        if not resultado:
            lbl_erro.value = "Não foi possível salvar o cliente. Verifique os dados e tente novamente."
            page.update()
            return

        dialog.open = False
        atualizar_tabela()

        snack_sucesso(page, f"Cliente '{tf_nome.value}' cadastrado com sucesso.")
        # FIX (logs mais detalhados): inclui id gerado, tipo,
        # documento e sigla no log — antes só registrava o nome.
        log_acao(
            page,
            f"Cliente cadastrado: '{tf_nome.value}'",
            f"cliente_id={resultado.get('id')} tipo={dd_tipo.value} "
            f"documento={tf_documento.value} sigla={sigla_auto}",
        )

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
                lbl_erro,
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

    lbl_erro = ft.Text("", color=ft.Colors.RED_700, size=12)

    # -------------------------
    # SALVAR
    # -------------------------
    async def salvar(e):

        lbl_erro.value = ""

        if not tf_nome.value or not dd_tipo.value or not tf_documento.value:
            lbl_erro.value = "Preencha todos os campos obrigatórios."
            page.update()
            return

        # FIX (logs mais detalhados): captura o que MUDOU, comparando
        # os valores originais do cliente com os novos valores dos
        # campos, antes de salvar — para o log dizer exatamente o que
        # foi alterado, não só "cliente editado".
        mudancas = []
        if (cliente.get("nome") or "") != tf_nome.value:
            mudancas.append(f"nome: '{cliente.get('nome') or ''}' -> '{tf_nome.value}'")
        if (cliente.get("tipo") or "") != dd_tipo.value:
            mudancas.append(f"tipo: '{cliente.get('tipo') or ''}' -> '{dd_tipo.value}'")
        if (cliente.get("documento") or "") != tf_documento.value:
            mudancas.append(f"documento: '{cliente.get('documento') or ''}' -> '{tf_documento.value}'")

        try:
            resultado = await run_db(
                page,
                update_cliente,
                cliente["id"],
                {
                    "nome": tf_nome.value,
                    "tipo": dd_tipo.value,
                    "documento": tf_documento.value,
                },
            )

        except Exception as ex:
            snack_erro(page, ex, contexto="atualizar o cliente")
            return

        if not resultado:
            lbl_erro.value = "Não foi possível atualizar o cliente. Tente novamente."
            page.update()
            return

        dialog.open = False

        on_save()

        snack_sucesso(page, "Cliente atualizado com sucesso.")
        detalhe_log = (
            f"cliente_id={cliente.get('id')} — " + "; ".join(mudancas)
            if mudancas else
            f"cliente_id={cliente.get('id')} (nenhum campo alterado)"
        )
        log_acao(page, f"Cliente editado: '{tf_nome.value}'", detalhe_log)

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
                lbl_erro,
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