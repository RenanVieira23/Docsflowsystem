import flet as ft
import asyncio

from database.models import (
    get_vinculos,
    add_vinculo,
    update_vinculo,
    delete_vinculo,
)

# ======================================================
# TAB CRUD GENÉRICA
# ======================================================

class CrudTiposTab(ft.Column):

    def __init__(
        self,
        page: ft.Page,
        titulo: str,
        descricao: str,
        get_func,
        add_func,
        update_func,
        delete_func,
        campo_nome="tipo",
    ):
        super().__init__(expand=True, spacing=12)

        self.page = page
        self.get_func = get_func
        self.add_func = add_func
        self.update_func = update_func
        self.delete_func = delete_func
        self.campo_nome = campo_nome

        self.dados = []

        # ---------------------
        # LOADING
        # ---------------------
        self.loading = ft.ProgressRing(visible=False, width=20, height=20)

        # ---------------------
        # INPUT
        # ---------------------
        self.tf_novo = ft.TextField(label=f"Novo {titulo}", width=340)

        self.btn_add = ft.FilledButton(
            "Adicionar",
            on_click=self.adicionar,
        )

        self.lista = ft.Column(spacing=6)

        # ---------------------
        # LAYOUT
        # ---------------------
        self.controls.extend([
            ft.Row(
                [
                    ft.Text(titulo, size=22, weight=ft.FontWeight.BOLD),
                    self.loading,
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),

            ft.Text(descricao, color=ft.Colors.GREY_600),

            ft.Divider(),

            ft.Container(
                padding=16,
                border_radius=10,
                bgcolor=ft.Colors.BLUE_50,
                border=ft.border.all(1, ft.Colors.BLUE_100),
                content=ft.Row([self.tf_novo, self.btn_add]),
            ),

            ft.Divider(),

            ft.Container(
                expand=True,
                content=ft.Column(
                    [self.lista],
                    scroll=ft.ScrollMode.AUTO,
                    expand=True,
                ),
            ),
        ])

        self.page.run_task(self._carregar)

    # ======================================================
    # LOAD
    # ======================================================

    async def _carregar(self):

        self.loading.visible = True
        self.page.update()

        try:
            dados = await asyncio.to_thread(self.get_func)
        except Exception as ex:
            print("Erro:", ex)
            dados = []

        self.dados = dados or []

        self.loading.visible = False
        self._renderizar()

    # ======================================================

    def _renderizar(self):

        self.lista.controls.clear()

        if not self.dados:
            self.lista.controls.append(
                ft.Text(
                    "Nenhum registro cadastrado.",
                    italic=True,
                    color=ft.Colors.GREY_500,
                )
            )

        for item in self.dados:
            self._add_item(item)

        self.lista.update()

    # ======================================================

    def _add_item(self, item):

        tf = ft.TextField(
            value=item.get(self.campo_nome, ""),
            read_only=True,
            dense=True,
            width=280,
        )

        btn_edit = ft.IconButton(
            ft.Icons.EDIT_OUTLINED,
            on_click=lambda e: self._editar(row),
        )

        btn_save = ft.IconButton(
            ft.Icons.CHECK,
            visible=False,
            icon_color=ft.Colors.GREEN,
            on_click=lambda e: self._salvar(item, tf),
        )

        btn_cancel = ft.IconButton(
            ft.Icons.CLOSE,
            visible=False,
            on_click=lambda e: self._cancelar(item, tf, row),
        )

        btn_delete = ft.IconButton(
            ft.Icons.DELETE_OUTLINE,
            icon_color=ft.Colors.RED_400,
            on_click=lambda e: self._excluir(item),
        )

        row = ft.Container(
            padding=10,
            border_radius=8,
            border=ft.border.all(1, ft.Colors.GREY_200),
            bgcolor=ft.Colors.WHITE,
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.LABEL_OUTLINE),
                    tf,
                    btn_edit,
                    btn_save,
                    btn_cancel,
                    btn_delete,
                ]
            ),
        )

        row.data = {
            "tf": tf,
            "edit": btn_edit,
            "save": btn_save,
            "cancel": btn_cancel,
            "delete": btn_delete,
        }

        self.lista.controls.append(row)

    # ======================================================
    # CRUD
    # ======================================================

    def adicionar(self, e):

        nome = (self.tf_novo.value or "").strip()
        if not nome:
            return

        self.add_func(nome)

        self.tf_novo.value = ""
        self.page.run_task(self._carregar)
        self._toast("Adicionado com sucesso.")

    # ---------------------

    def _editar(self, row):
        d = row.data
        d["tf"].read_only = False
        d["edit"].visible = False
        d["save"].visible = True
        d["cancel"].visible = True
        d["delete"].visible = False
        self.page.update()

    # ---------------------

    def _salvar(self, item, tf):

        nome = (tf.value or "").strip()
        if not nome:
            return

        self.update_func(item["id"], {"tipo": nome})

        self.page.run_task(self._carregar)
        self._toast("Atualizado.")

    # ---------------------

    def _cancelar(self, item, tf, row):

        d = row.data

        tf.value = item.get(self.campo_nome, "")
        tf.read_only = True

        d["edit"].visible = True
        d["save"].visible = False
        d["cancel"].visible = False
        d["delete"].visible = True

        self.page.update()

    # ---------------------

    def _excluir(self, item):

        self.delete_func(item["id"])

        self.page.run_task(self._carregar)
        self._toast("Excluído.")

    # ---------------------

    def _toast(self, msg):
        self.page.snack_bar = ft.SnackBar(ft.Text(msg))
        self.page.snack_bar.open = True
        self.page.update()


# ======================================================
# ⭐ MANTÉM NOME ANTIGO (COMPATIBILIDADE TOTAL)
# ======================================================

class TiposPartesView(ft.Column):

    def __init__(self, page: ft.Page):
        super().__init__(expand=True)

        self.controls.append(
            ft.Tabs(
                expand=True,
                tabs=[
                    ft.Tab(
                        text="Tipos de Partes ",
                        content=CrudTiposTab(
                            page,
                            titulo="Vínculos",
                            descricao="Tipos de vínculo que uma parte possui no contrato.",
                            get_func=get_vinculos,
                            add_func=add_vinculo,
                            update_func=update_vinculo,
                            delete_func=delete_vinculo,
                        ),
                    ),

                    ft.Tab(
                        text="Tipos de Contrato",
                        content=ft.Container(
                            padding=20,
                            content=ft.Text("Estrutura pronta."),
                        ),
                    ),

                    ft.Tab(
                        text="Tipos de Prazos",
                        content=ft.Container(
                            padding=20,
                            content=ft.Text("Estrutura futura."),
                        ),
                    ),
                ],
            )
        )


# ======================================================
# EXPORT (NOME ANTIGO)
# ======================================================

def tipos_partes_view(page: ft.Page):
    return TiposPartesView(page)