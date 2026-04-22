import flet as ft
import asyncio

from database.models import (

    # PARTES
    get_tipos_partes,
    add_tipo_parte,
    update_tipo_parte,
    delete_tipo_parte,

    # CONTRATOS
    get_tipos_contratos,
    add_tipo_contrato,
    update_tipo_contrato,
    delete_tipo_contrato,

    # PRAZOS
    get_tipos_prazos,
    add_tipo_prazo,
    update_tipo_prazo,
    delete_tipo_prazo,
)


# ======================================================
# VIEW
# ======================================================

class TiposPartesView(ft.Column):

    def __init__(self, page: ft.Page):
        super().__init__(expand=True, scroll=ft.ScrollMode.AUTO, spacing=30)

        self.app_page = page

        # =========================
        # LISTAS
        # =========================

        self.lista_partes = ft.Column()
        self.lista_contratos = ft.Column()
        self.lista_prazos = ft.Column()

        # =========================
        # INPUTS
        # =========================

        self.tf_parte = ft.TextField(label="Novo tipo de parte")
        self.tf_contrato = ft.TextField(label="Novo tipo de contrato")
        self.tf_prazo = ft.TextField(label="Novo tipo de prazo")

        # =========================
        # LAYOUT
        # =========================

        self.controls = [

            self._bloco(
                "Tipos de Partes",
                self.tf_parte,
                lambda e: self._add_parte(),
                self.lista_partes
            ),

            self._bloco(
                "Tipos de Contratos",
                self.tf_contrato,
                lambda e: self._add_contrato(),
                self.lista_contratos
            ),

            self._bloco(
                "Tipos de Prazos",
                self.tf_prazo,
                lambda e: self._add_prazo(),
                self.lista_prazos
            ),
        ]

        page.run_task(self._carregar_tudo)

    # ======================================================
    # BLOCO VISUAL
    # ======================================================

    def _bloco(self, titulo, campo, acao, lista):

        return ft.Container(
            padding=20,
            border_radius=12,
            bgcolor=ft.Colors.WHITE,
            border=ft.border.all(1, ft.Colors.GREY_200),
            content=ft.Column([
                ft.Text(titulo, size=22, weight=ft.FontWeight.BOLD),

                ft.Row([
                    campo,
                    ft.FilledButton("Adicionar", on_click=acao)
                ]),

                lista
            ])
        )

    # ======================================================
    # LOAD
    # ======================================================

    async def _carregar_tudo(self):

        partes = await asyncio.to_thread(get_tipos_partes)
        contratos = await asyncio.to_thread(get_tipos_contratos)
        prazos = await asyncio.to_thread(get_tipos_prazos)

        self._render_lista(partes, self.lista_partes,
                           update_tipo_parte, delete_tipo_parte)

        self._render_lista(contratos, self.lista_contratos,
                           update_tipo_contrato, delete_tipo_contrato)

        self._render_lista(prazos, self.lista_prazos,
                           update_tipo_prazo, delete_tipo_prazo)

        self.update()

    # ======================================================
    # RENDER LISTA
    # ======================================================

    def _render_lista(self, dados, lista, update_func, delete_func):

        lista.controls.clear()

        for item in dados:

            tf = ft.TextField(
                value=item["nome"],
                read_only=True,
                width=300,
                dense=True
            )

            def salvar(e, i=item, t=tf):
                update_func(i["id"], {"nome": t.value})
                self.page.run_task(self._carregar_tudo)

            def excluir(e, i=item):
                delete_func(i["id"])
                self.page.run_task(self._carregar_tudo)

            lista.controls.append(

                ft.Row([
                    tf,

                    ft.IconButton(
                        ft.Icons.EDIT,
                        on_click=lambda e, t=tf: self._editar(t)
                    ),

                    ft.IconButton(
                        ft.Icons.CHECK,
                        icon_color=ft.Colors.GREEN,
                        on_click=salvar
                    ),

                    ft.IconButton(
                        ft.Icons.DELETE,
                        icon_color=ft.Colors.RED,
                        on_click=excluir
                    ),
                ])
            )

    # ======================================================
    # EDITAR
    # ======================================================

    def _editar(self, tf):
        tf.read_only = False
        tf.focus()
        self.update()

    # ======================================================
    # ADD
    # ======================================================

    def _add_parte(self):
        nome = self.tf_parte.value.strip()
        if nome:
            add_tipo_parte(nome)
            self.tf_parte.value = ""
            self.page.run_task(self._carregar_tudo)

    def _add_contrato(self):
        nome = self.tf_contrato.value.strip()
        if nome:
            add_tipo_contrato(nome)
            self.tf_contrato.value = ""
            self.page.run_task(self._carregar_tudo)

    def _add_prazo(self):
        nome = self.tf_prazo.value.strip()
        if nome:
            add_tipo_prazo(nome)
            self.tf_prazo.value = ""
            self.page.run_task(self._carregar_tudo)


# ======================================================
# EXPORT
# ======================================================

def tipos_partes_view(page: ft.Page):
    return TiposPartesView(page)