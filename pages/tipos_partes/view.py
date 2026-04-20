import flet as ft
import asyncio

from database.models import (
    get_tipos_partes,
    add_tipo_parte,
    update_tipo_parte,
    delete_tipo_parte,
)


# ======================================================
# VIEW
# ======================================================

class TiposPartesView(ft.Column):

    def __init__(self, page: ft.Page):
        super().__init__(expand=True, spacing=12)

        self.app_page = page
        self.tipos = []

        # =========================
        # LOADING
        # =========================
        self.loading = ft.ProgressRing(
            visible=False, width=22, height=22, stroke_width=2
        )

        # =========================
        # CAMPO NOVO TIPO (inline)
        # =========================
        self.tf_novo = ft.TextField(
            label="Nome do tipo (ex: Réu, Sócio, Fiador...)",
            width=340,
        )

        self.btn_adicionar = ft.FilledButton(
            "Adicionar",
            height=38,
            on_click=self.adicionar,
        )

        # =========================
        # LISTA
        # =========================
        self.lista = ft.Column(spacing=6)

        # =========================
        # LAYOUT
        # =========================
        self.controls.extend([

            ft.Row(
                [
                    ft.Text(
                        "Tipos de Partes",
                        size=22,
                        weight=ft.FontWeight.BOLD,
                    ),
                    self.loading,
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),

            ft.Text(
                "Cadastre os tipos de vínculo que uma parte pode ter em um contrato "
                "(ex: Réu, Autor, Sócio, Fiador, Testemunha...)",
                color=ft.Colors.GREY_600,
                size=13,
            ),

            ft.Divider(),

            # ADICIONAR NOVO
            ft.Container(
                padding=16,
                border_radius=10,
                bgcolor=ft.Colors.BLUE_50,
                border=ft.border.all(1, ft.Colors.BLUE_100),
                content=ft.Row(
                    [
                        self.tf_novo,
                        self.btn_adicionar,
                    ],
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ),

            ft.Divider(),

            # LISTA DE TIPOS
            ft.Container(
                expand=True,
                content=ft.Column(
                    [self.lista],
                    scroll=ft.ScrollMode.AUTO,
                    expand=True,
                ),
            ),
        ])

        self.app_page.run_task(self._carregar)


    # ======================================================
    # CARREGAR
    # ======================================================

    async def _carregar(self):

        self.loading.visible = True
        self.app_page.update()

        try:
            dados = await asyncio.to_thread(get_tipos_partes)
        except Exception as ex:
            print("Erro tipos_partes:", ex)
            dados = []

        self.tipos = dados or []
        self.loading.visible = False
        self._renderizar_lista()


    def _renderizar_lista(self):

        self.lista.controls.clear()

        if not self.tipos:
            self.lista.controls.append(
                ft.Text(
                    "Nenhum tipo cadastrado ainda.",
                    color=ft.Colors.GREY_500,
                    italic=True,
                )
            )

        for t in self.tipos:
            self._adicionar_item_lista(t)

        self.lista.update()


    def _adicionar_item_lista(self, tipo: dict):

        tf_edit = ft.TextField(
            value=tipo.get("nome", ""),
            dense=True,
            width=280,
            read_only=True,
        )

        btn_editar = ft.IconButton(
            icon=ft.Icons.EDIT_OUTLINED,
            tooltip="Editar",
            icon_size=18,
            on_click=lambda e, t=tipo, tf=tf_edit, b=None: self._modo_edicao(t, tf, row),
        )

        btn_salvar = ft.IconButton(
            icon=ft.Icons.CHECK,
            tooltip="Salvar",
            icon_size=18,
            visible=False,
            icon_color=ft.Colors.GREEN,
            on_click=lambda e, t=tipo, tf=tf_edit: self._salvar_edicao(t, tf, row),
        )

        btn_cancelar = ft.IconButton(
            icon=ft.Icons.CLOSE,
            tooltip="Cancelar",
            icon_size=18,
            visible=False,
            icon_color=ft.Colors.GREY,
            on_click=lambda e, t=tipo, tf=tf_edit: self._cancelar_edicao(t, tf, row),
        )

        btn_excluir = ft.IconButton(
            icon=ft.Icons.DELETE_OUTLINE,
            tooltip="Excluir",
            icon_size=18,
            icon_color=ft.Colors.RED_400,
            on_click=lambda e, t=tipo: self._confirmar_exclusao(t),
        )

        row = ft.Container(
            padding=ft.padding.symmetric(vertical=4, horizontal=12),
            border_radius=8,
            bgcolor=ft.Colors.WHITE,
            border=ft.border.all(1, ft.Colors.GREY_200),
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.LABEL_OUTLINE, size=16, color=ft.Colors.BLUE_400),
                    tf_edit,
                    btn_editar,
                    btn_salvar,
                    btn_cancelar,
                    btn_excluir,
                ],
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

        # Guarda referências nos botões para manipular o row depois
        row.data = {
            "tipo": tipo,
            "tf": tf_edit,
            "btn_editar": btn_editar,
            "btn_salvar": btn_salvar,
            "btn_cancelar": btn_cancelar,
            "btn_excluir": btn_excluir,
        }

        self.lista.controls.append(row)


    # ======================================================
    # ADICIONAR
    # ======================================================

    def adicionar(self, e):

        nome = (self.tf_novo.value or "").strip()

        if not nome:
            self.app_page.snack_bar = ft.SnackBar(ft.Text("Digite o nome do tipo."))
            self.app_page.snack_bar.open = True
            self.app_page.update()
            return

        try:
            novo = add_tipo_parte(nome)
        except Exception as ex:
            self.app_page.snack_bar = ft.SnackBar(ft.Text(f"Erro: {ex}"))
            self.app_page.snack_bar.open = True
            self.app_page.update()
            return

        self.tf_novo.value = ""
        self.app_page.run_task(self._carregar)

        self.app_page.snack_bar = ft.SnackBar(ft.Text(f"Tipo '{nome}' adicionado."))
        self.app_page.snack_bar.open = True
        self.app_page.update()


    # ======================================================
    # EDIÇÃO INLINE
    # ======================================================

    def _modo_edicao(self, tipo, tf, row):
        d = row.data
        tf.read_only = False
        tf.focus()
        d["btn_editar"].visible = False
        d["btn_salvar"].visible = True
        d["btn_cancelar"].visible = True
        d["btn_excluir"].visible = False
        self.app_page.update()


    def _salvar_edicao(self, tipo, tf, row):
        nome = (tf.value or "").strip()

        if not nome:
            return

        try:
            update_tipo_parte(tipo["id"], {"nome": nome})
        except Exception as ex:
            self.app_page.snack_bar = ft.SnackBar(ft.Text(f"Erro: {ex}"))
            self.app_page.snack_bar.open = True
            self.app_page.update()
            return

        self.app_page.run_task(self._carregar)

        self.app_page.snack_bar = ft.SnackBar(ft.Text("Tipo atualizado."))
        self.app_page.snack_bar.open = True
        self.app_page.update()


    def _cancelar_edicao(self, tipo, tf, row):
        d = row.data
        tf.value = tipo.get("nome", "")
        tf.read_only = True
        d["btn_editar"].visible = True
        d["btn_salvar"].visible = False
        d["btn_cancelar"].visible = False
        d["btn_excluir"].visible = True
        self.app_page.update()


    # ======================================================
    # EXCLUSÃO
    # ======================================================

    def _confirmar_exclusao(self, tipo):

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Confirmar exclusão"),
            content=ft.Text(
                f"Excluir o tipo '{tipo['nome']}'?\n\n"
                "Contratos que já usam este tipo não serão afetados."
            ),
            actions=[
                ft.TextButton(
                    "Cancelar",
                    on_click=lambda e: self._fechar(dialog),
                ),
                ft.FilledButton(
                    "Excluir",
                    style=ft.ButtonStyle(bgcolor=ft.Colors.RED),
                    on_click=lambda e: self._excluir(tipo, dialog),
                ),
            ],
        )

        self.app_page.overlay.append(dialog)
        dialog.open = True
        self.app_page.update()


    def _excluir(self, tipo, dialog):
        try:
            delete_tipo_parte(tipo["id"])
        except Exception as ex:
            self.app_page.snack_bar = ft.SnackBar(ft.Text(f"Erro: {ex}"))
            self.app_page.snack_bar.open = True

        dialog.open = False
        self.app_page.run_task(self._carregar)

        self.app_page.snack_bar = ft.SnackBar(ft.Text(f"Tipo '{tipo['nome']}' excluído."))
        self.app_page.snack_bar.open = True
        self.app_page.update()


    def _fechar(self, dialog):
        dialog.open = False
        self.app_page.update()


# ======================================================
# EXPORT
# ======================================================

def tipos_partes_view(page: ft.Page):
    return TiposPartesView(page)
