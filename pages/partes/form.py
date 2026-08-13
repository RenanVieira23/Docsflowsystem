import flet as ft
from database.models import add_parte, update_parte
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
# NOVA PARTE
# ======================================================

def nova_parte_dialog(page: ft.Page, on_save):

    tf_nome = ft.TextField(label="Nome completo", autofocus=True, width=380)

    dd_tipo = ft.Dropdown(
        label="Tipo",
        width=380,
        options=[
            ft.dropdown.Option("Física"),
            ft.dropdown.Option("Jurídica"),
        ],
    )

    tf_documento = ft.TextField(label="Documento (CPF / CNPJ)", width=380)

    lbl_erro = ft.Text("", color=ft.Colors.RED_700, size=12)

    async def salvar(e):

        lbl_erro.value = ""

        if not tf_nome.value or not dd_tipo.value or not tf_documento.value:
            lbl_erro.value = "Preencha todos os campos obrigatórios."
            page.update()
            return

        # FIX: tenant_id é obrigatório para passar na política RLS de
        # INSERT (ver database/models.py -> add_parte). Sem isso, o
        # backend recusa a operação, que é exatamente o erro relatado.
        tenant_id = page.local_store.get("tenant_id")
        if not tenant_id:
            lbl_erro.value = "Sessão sem tenant_id — faça login novamente."
            page.update()
            return

        try:
            # FIX: chamado via run_db (não mais direto/síncrono) para
            # garantir que a operação rode com o client autenticado
            # da sessão atual, e não com um client anônimo sem token.
            resultado = await run_db(page, add_parte, {
                "nome": tf_nome.value.strip(),
                "tipo": dd_tipo.value,
                "documento": tf_documento.value.strip(),
                "tenant_id": tenant_id,
            })
        except Exception as ex:
            snack_erro(page, ex, contexto="salvar a parte")
            return

        if not resultado:
            lbl_erro.value = "Não foi possível salvar a parte. Verifique os dados e tente novamente."
            page.update()
            return

        dialog.open = False
        on_save()
        snack_sucesso(page, f"Parte '{tf_nome.value}' cadastrada com sucesso.")
        log_acao(page, f"Parte cadastrada: '{tf_nome.value}'")
        page.update()


    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Nova Parte"),
        content=ft.Column(
            [tf_nome, dd_tipo, tf_documento, lbl_erro],
            spacing=10,
            tight=True,
        ),
        actions=[
            ft.TextButton("Cancelar", on_click=lambda e: _fechar(dialog, page)),
            ft.FilledButton("Salvar", on_click=salvar),
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

    lbl_erro = ft.Text("", color=ft.Colors.RED_700, size=12)

    async def salvar(e):

        lbl_erro.value = ""

        if not tf_nome.value or not dd_tipo.value or not tf_documento.value:
            lbl_erro.value = "Preencha todos os campos obrigatórios."
            page.update()
            return

        try:
            # FIX: idem nova_parte_dialog — via run_db, com client
            # autenticado da sessão atual.
            resultado = await run_db(page, update_parte, parte["id"], {
                "nome": tf_nome.value.strip(),
                "tipo": dd_tipo.value,
                "documento": tf_documento.value.strip(),
            })
        except Exception as ex:
            snack_erro(page, ex, contexto="atualizar a parte")
            return

        if not resultado:
            lbl_erro.value = "Não foi possível atualizar a parte. Tente novamente."
            page.update()
            return

        dialog.open = False
        on_save()
        snack_sucesso(page, "Parte atualizada com sucesso.")
        log_acao(page, f"Parte editada: '{tf_nome.value}'", f"parte_id={parte['id']}")
        page.update()


    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Editar Parte"),
        content=ft.Column(
            [tf_nome, dd_tipo, tf_documento, lbl_erro],
            spacing=10,
            tight=True,
        ),
        actions=[
            ft.TextButton("Cancelar", on_click=lambda e: _fechar(dialog, page)),
            ft.FilledButton("Salvar alterações", on_click=salvar),
        ],
        actions_alignment="end",
    )

    return dialog