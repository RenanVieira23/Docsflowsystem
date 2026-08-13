"""
pages/tipos_partes/view.py
===========================
Página unificada de Tipos com 3 seções:
  1. Tipos de Partes  → tabela vinculos  (campo "tipo", multi-tenant)
  2. Tipos de Contrato→ tabela tipos_contratos (campo "nome")
  3. Tipos de Prazos  → tabela tipos_prazos    (campo "nome")

FIX (versão anterior):
  - Todos os handlers que escrevem no banco (_add_parte, _add_contrato,
    _add_prazo, _salvar de cada linha, _excluir_vinculo, _excluir_nome)
    agora são `async def` e chamam o banco via run_db(self.app_page, ...),
    garantindo que rodem com o client AUTENTICADO da sessão.

FIX (esta versão):
  - Mensagens de erro amigáveis via utils/erros_ui, em vez de expor
    a exceção crua (`f"Erro: {ex}"`) na tela.
"""

import flet as ft

from database.models import (
    # ── vinculos (tipos de partes) ──
    get_vinculos,
    add_vinculo,
    update_vinculo,
    delete_vinculo,

    # ── tipos de contratos ──
    get_tipos_contratos,
    add_tipo_contrato,
    update_tipo_contrato,
    delete_tipo_contrato,

    # ── tipos de prazos ──
    get_tipos_prazos,
    add_tipo_prazo,
    update_tipo_prazo,
    delete_tipo_prazo,
)
from database.supabase_client import run_db
from utils.permissoes import pode
from utils.erros_ui import snack_erro, snack_sucesso, banner_erro_carregamento


# ======================================================
# VIEW
# ======================================================

class TiposPartesView(ft.Column):

    def __init__(self, page: ft.Page):
        super().__init__(expand=True, scroll=ft.ScrollMode.AUTO, spacing=30)

        self.app_page  = page   # ← sempre usar self.app_page, não self.page
        self.tenant_id = page.local_store.get("tenant_id") if hasattr(page, "local_store") else None

        # ── listas dinâmicas ──
        self.lista_partes    = ft.Column(spacing=4)
        self.lista_contratos = ft.Column(spacing=4)
        self.lista_prazos    = ft.Column(spacing=4)

        # ── campos de novo item ──
        self.tf_parte    = ft.TextField(label="Nova categoria de parte (ex: Réu, Autor...)",    expand=True, dense=True)
        self.tf_contrato = ft.TextField(label="Nova categoria de contrato (ex: Locação...)",    expand=True, dense=True)
        self.tf_prazo    = ft.TextField(label="Nova categoria de prazo (ex: Vencimento...)",    expand=True, dense=True)

        # ── área de erro de carregamento (uma para as 3 seções) ──
        self.area_erro = ft.Container(visible=False)

        # ── layout ──
        self.controls = [
            self.area_erro,
            self._bloco(
                "Categorias de Partes",
                "Tipos de vínculo das partes nos contratos (tabela vínculos)",
                self.tf_parte,
                lambda e: self.app_page.run_task(self._add_parte),
                self.lista_partes,
            ),
            self._bloco(
                "Categorias de Contratos",
                "Classificações de contratos",
                self.tf_contrato,
                lambda e: self.app_page.run_task(self._add_contrato),
                self.lista_contratos,
            ),
            self._bloco(
                "Categorias de Prazos",
                "Classificações de prazos e alertas",
                self.tf_prazo,
                lambda e: self.app_page.run_task(self._add_prazo),
                self.lista_prazos,
            ),
        ]

        page.run_task(self._carregar_tudo)   # ← page (não self.page)

    # ======================================================
    # BLOCO VISUAL
    # ======================================================

    def _bloco(self, titulo, descricao, campo, acao, lista):
        pode_cadastrar = pode(self.app_page, "categorias", "cadastrar")
        return ft.Container(
            padding=20,
            border_radius=12,
            bgcolor=ft.Colors.WHITE,
            border=ft.border.all(1, ft.Colors.GREY_200),
            content=ft.Column([
                ft.Text(titulo, size=18, weight=ft.FontWeight.BOLD),
                ft.Text(descricao, size=12, color=ft.Colors.GREY_600),
                ft.Container(
                    padding=12, border_radius=8,
                    bgcolor=ft.Colors.BLUE_50,
                    border=ft.border.all(1, ft.Colors.BLUE_100),
                    visible=pode_cadastrar,
                    content=ft.Row([
                        campo,
                        ft.FilledButton("Adicionar", height=36, on_click=acao),
                    ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ),
                ft.Divider(height=1),
                ft.Container(
                    content=ft.Column([lista], scroll=ft.ScrollMode.AUTO),
                    height=300,
                ),
            ], spacing=10),
        )

    # ======================================================
    # LOAD
    # ======================================================

    async def _carregar_tudo(self):
        erro = False
        try:
            # vinculos precisam de tenant_id
            partes    = await run_db(self.app_page, get_vinculos, self.tenant_id)
            contratos = await run_db(self.app_page, get_tipos_contratos, self.tenant_id)
            prazos    = await run_db(self.app_page, get_tipos_prazos, self.tenant_id)
        except Exception as ex:
            print("Erro tipos:", ex)
            partes = contratos = prazos = []
            erro = True

        self.area_erro.visible = erro
        if erro:
            self.area_erro.content = banner_erro_carregamento(
                "as categorias", on_retry=lambda e: self.app_page.run_task(self._carregar_tudo)
            )

        # Tipos de partes: campo "tipo", update via update_vinculo, delete via delete_vinculo
        self._render_lista_vinculos(partes or [], self.lista_partes)

        # Tipos de contrato e prazo: campo "nome"
        self._render_lista_nome(contratos or [], self.lista_contratos,
                                update_tipo_contrato, delete_tipo_contrato)
        self._render_lista_nome(prazos or [], self.lista_prazos,
                                update_tipo_prazo, delete_tipo_prazo)

        self.app_page.update()

    # ======================================================
    # RENDER — vínculos (campo "tipo")
    # ======================================================

    def _render_lista_vinculos(self, dados, lista):
        lista.controls.clear()

        if not dados:
            lista.controls.append(
                ft.Text("Nenhuma categoria cadastrada.", color=ft.Colors.GREY_500, italic=True, size=13))
            return

        for item in dados:
            tf = ft.TextField(
                value=item.get("tipo", ""),
                read_only=True,
                width=260, dense=True,
            )

            btn_editar  = ft.IconButton(icon=ft.Icons.EDIT_OUTLINED,  icon_size=18, tooltip="Editar",
                                        visible=pode(self.app_page, "categorias", "editar"))
            btn_salvar  = ft.IconButton(icon=ft.Icons.CHECK, icon_size=18, visible=False,
                                        icon_color=ft.Colors.GREEN, tooltip="Salvar")
            btn_cancelar= ft.IconButton(icon=ft.Icons.CLOSE, icon_size=18, visible=False,
                                        icon_color=ft.Colors.GREY,  tooltip="Cancelar")
            btn_excluir = ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_size=18,
                                        icon_color=ft.Colors.RED_400, tooltip="Excluir",
                                        visible=pode(self.app_page, "categorias", "editar"))

            row = ft.Container(
                padding=ft.padding.symmetric(vertical=4, horizontal=10),
                border_radius=8, bgcolor=ft.Colors.GREY_50,
                border=ft.border.all(1, ft.Colors.GREY_200),
                content=ft.Row(
                    [ft.Icon(ft.Icons.LABEL_OUTLINE, size=14, color=ft.Colors.BLUE_400),
                     tf, btn_editar, btn_salvar, btn_cancelar, btn_excluir],
                    spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            )

            _original = item.get("tipo", "")

            def _editar(e, t=tf, be=btn_editar, bs=btn_salvar, bc=btn_cancelar, bx=btn_excluir):
                t.read_only = False
                be.visible = False; bs.visible = True; bc.visible = True; bx.visible = False
                self.app_page.update()

            async def _salvar(e, i=item, t=tf):
                novo = (t.value or "").strip()
                if not novo:
                    return
                try:
                    resultado = await run_db(self.app_page, update_vinculo, i["id"], {"tipo": novo})
                except Exception as ex:
                    snack_erro(self.app_page, ex, contexto="atualizar a categoria")
                    return
                if isinstance(resultado, dict) and resultado.get("_error"):
                    snack_erro(self.app_page, Exception(resultado["_error"]), contexto="atualizar a categoria")
                    return
                self.app_page.run_task(self._carregar_tudo)
                snack_sucesso(self.app_page, "Categoria atualizada.")

            def _cancelar(e, t=tf, orig=_original,
                          be=btn_editar, bs=btn_salvar, bc=btn_cancelar, bx=btn_excluir):
                t.value = orig; t.read_only = True
                be.visible = True; bs.visible = False; bc.visible = False; bx.visible = True
                self.app_page.update()

            def _confirmar_del(e, i=item):
                dlg = ft.AlertDialog(
                    modal=True,
                    title=ft.Text("Confirmar exclusão"),
                    content=ft.Text(f"Excluir a categoria '{i.get('tipo')}'?"),
                    actions=[
                        ft.TextButton("Cancelar", on_click=lambda e, d=None: self._fechar(dlg)),
                        ft.FilledButton("Excluir",
                                        style=ft.ButtonStyle(bgcolor=ft.Colors.RED),
                                        on_click=lambda e, ii=i: self.app_page.run_task(self._excluir_vinculo, ii, dlg)),
                    ],
                )
                self.app_page.overlay.append(dlg)
                dlg.open = True
                self.app_page.update()

            btn_editar.on_click   = _editar
            btn_salvar.on_click   = _salvar
            btn_cancelar.on_click = _cancelar
            btn_excluir.on_click  = _confirmar_del

            lista.controls.append(row)

    # ======================================================
    # RENDER — genérico campo "nome"
    # ======================================================

    def _render_lista_nome(self, dados, lista, update_func, delete_func):
        lista.controls.clear()

        if not dados:
            lista.controls.append(
                ft.Text("Nenhuma categoria cadastrada.", color=ft.Colors.GREY_500, italic=True, size=13))
            return

        for item in dados:
            tf = ft.TextField(
                value=item.get("nome", ""),
                read_only=True, width=260, dense=True,
            )

            btn_editar  = ft.IconButton(icon=ft.Icons.EDIT_OUTLINED,  icon_size=18,
                                        visible=pode(self.app_page, "categorias", "editar"))
            btn_salvar  = ft.IconButton(icon=ft.Icons.CHECK, icon_size=18, visible=False,
                                        icon_color=ft.Colors.GREEN)
            btn_cancelar= ft.IconButton(icon=ft.Icons.CLOSE, icon_size=18, visible=False,
                                        icon_color=ft.Colors.GREY)
            btn_excluir = ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_size=18,
                                        icon_color=ft.Colors.RED_400,
                                        visible=pode(self.app_page, "categorias", "editar"))

            row = ft.Container(
                padding=ft.padding.symmetric(vertical=4, horizontal=10),
                border_radius=8, bgcolor=ft.Colors.GREY_50,
                border=ft.border.all(1, ft.Colors.GREY_200),
                content=ft.Row(
                    [ft.Icon(ft.Icons.LABEL_OUTLINE, size=14, color=ft.Colors.BLUE_400),
                     tf, btn_editar, btn_salvar, btn_cancelar, btn_excluir],
                    spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            )

            _original = item.get("nome", "")

            def _editar(e, t=tf, be=btn_editar, bs=btn_salvar, bc=btn_cancelar, bx=btn_excluir):
                t.read_only = False
                be.visible = False; bs.visible = True; bc.visible = True; bx.visible = False
                self.app_page.update()

            async def _salvar(e, i=item, t=tf, uf=update_func):
                novo = (t.value or "").strip()
                if not novo: return
                try:
                    resultado = await run_db(self.app_page, uf, i["id"], {"nome": novo})
                except Exception as ex:
                    snack_erro(self.app_page, ex, contexto="atualizar a categoria")
                    return
                if not resultado:
                    snack_erro(self.app_page, Exception("sem resultado"), contexto="atualizar a categoria")
                    return
                self.app_page.run_task(self._carregar_tudo)
                snack_sucesso(self.app_page, "Categoria atualizada.")

            def _cancelar(e, t=tf, orig=_original,
                          be=btn_editar, bs=btn_salvar, bc=btn_cancelar, bx=btn_excluir):
                t.value = orig; t.read_only = True
                be.visible = True; bs.visible = False; bc.visible = False; bx.visible = True
                self.app_page.update()

            def _confirmar_del(e, i=item, df=delete_func):
                dlg = ft.AlertDialog(
                    modal=True,
                    title=ft.Text("Confirmar exclusão"),
                    content=ft.Text(f"Excluir '{i.get('nome')}'?"),
                    actions=[
                        ft.TextButton("Cancelar", on_click=lambda e: self._fechar(dlg)),
                        ft.FilledButton("Excluir",
                                        style=ft.ButtonStyle(bgcolor=ft.Colors.RED),
                                        on_click=lambda e, ii=i, ddf=df: self.app_page.run_task(self._excluir_nome, ii, ddf, dlg)),
                    ],
                )
                self.app_page.overlay.append(dlg)
                dlg.open = True
                self.app_page.update()

            btn_editar.on_click   = _editar
            btn_salvar.on_click   = _salvar
            btn_cancelar.on_click = _cancelar
            btn_excluir.on_click  = _confirmar_del

            lista.controls.append(row)

    # ======================================================
    # ADD
    # ======================================================

    async def _add_parte(self):
        nome = (self.tf_parte.value or "").strip()
        if not nome:
            snack_erro(self.app_page, Exception("nome vazio"), contexto="adicionar a categoria")
            return
        if not self.tenant_id:
            snack_erro(self.app_page, Exception("sem tenant_id"), contexto="adicionar a categoria (faça login novamente)")
            return
        try:
            resultado = await run_db(self.app_page, add_vinculo, nome, self.tenant_id)
        except Exception as ex:
            snack_erro(self.app_page, ex, contexto="adicionar a categoria")
            return
        if isinstance(resultado, dict) and resultado.get("_error"):
            snack_erro(self.app_page, Exception(resultado["_error"]), contexto="adicionar a categoria")
            return
        self.tf_parte.value = ""
        self.app_page.run_task(self._carregar_tudo)
        snack_sucesso(self.app_page, f"'{nome}' adicionado.")

    async def _add_contrato(self):
        nome = (self.tf_contrato.value or "").strip()
        if not nome:
            snack_erro(self.app_page, Exception("nome vazio"), contexto="adicionar a categoria")
            return
        try:
            resultado = await run_db(self.app_page, add_tipo_contrato, nome, self.tenant_id)
        except Exception as ex:
            snack_erro(self.app_page, ex, contexto="adicionar a categoria")
            return
        if not resultado:
            snack_erro(self.app_page, Exception("sem resultado"), contexto="adicionar a categoria")
            return
        self.tf_contrato.value = ""
        self.app_page.run_task(self._carregar_tudo)
        snack_sucesso(self.app_page, f"'{nome}' adicionado.")

    async def _add_prazo(self):
        nome = (self.tf_prazo.value or "").strip()
        if not nome:
            snack_erro(self.app_page, Exception("nome vazio"), contexto="adicionar a categoria")
            return
        try:
            resultado = await run_db(self.app_page, add_tipo_prazo, nome, self.tenant_id)
        except Exception as ex:
            snack_erro(self.app_page, ex, contexto="adicionar a categoria")
            return
        if not resultado:
            snack_erro(self.app_page, Exception("sem resultado"), contexto="adicionar a categoria")
            return
        self.tf_prazo.value = ""
        self.app_page.run_task(self._carregar_tudo)
        snack_sucesso(self.app_page, f"'{nome}' adicionado.")

    # ======================================================
    # DELETE helpers
    # ======================================================

    async def _excluir_vinculo(self, item, dlg):
        try:
            await run_db(self.app_page, delete_vinculo, item["id"])
        except Exception as ex:
            snack_erro(self.app_page, ex, contexto="excluir a categoria")
        dlg.open = False
        self.app_page.run_task(self._carregar_tudo)
        self.app_page.update()

    async def _excluir_nome(self, item, delete_func, dlg):
        try:
            await run_db(self.app_page, delete_func, item["id"])
        except Exception as ex:
            snack_erro(self.app_page, ex, contexto="excluir a categoria")
        dlg.open = False
        self.app_page.run_task(self._carregar_tudo)
        self.app_page.update()

    def _fechar(self, dlg):
        dlg.open = False
        self.app_page.update()


def tipos_partes_view(page: ft.Page):
    return TiposPartesView(page)