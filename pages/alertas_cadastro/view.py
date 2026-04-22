"""
pages/alertas_cadastro/view.py
================================
Tela de Cadastro de Prazos:
  - Campo de busca global (qualquer coluna do contrato)
  - Lista de contratos correspondentes
  - Selecionar contrato → painel inline para adicionar prazo
  - Campos: Data do prazo, Tipo de prazo, Observação, Índice (auto)
"""
import flet as ft
import asyncio

from database.models import (
    get_contratos,
    get_clientes,
    get_tipos_prazos_db,
    add_prazo,
)
from utils.dataptbr import data_br_para_db, data_db_para_br
from utils.calendario_ptbr import calendario_ptbr


def _snack(page, msg):
    page.snack_bar = ft.SnackBar(ft.Text(msg))
    page.snack_bar.open = True
    page.update()


# ======================================================
# VIEW
# ======================================================

class AlertasCadastroView(ft.Column):

    def __init__(self, page: ft.Page):
        super().__init__(expand=True, spacing=12)
        self.app_page     = page
        self.tenant_id    = page.local_store.get("tenant_id") if hasattr(page, "local_store") else None
        self.contratos    = []
        self.filtrados    = []
        self.clientes_map = {}
        self.selecionado  = None

        self.loading = ft.ProgressRing(visible=False, width=18, height=18, stroke_width=2)

        self.tf_busca = ft.TextField(
            hint_text="Buscar contrato (apelido, cliente, índice...)",
            expand=True, height=38, on_change=self._filtrar,
        )

        self.lista_contratos = ft.Column(spacing=4, scroll=ft.ScrollMode.AUTO)

        self.painel_prazo = ft.Container(visible=False)

        self.controls.extend([
            ft.Row([
                ft.Text("Cadastro de Prazos", size=22, weight=ft.FontWeight.BOLD),
                self.loading,
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),

            ft.Text(
                "Busque um contrato e adicione prazos a ele.",
                color=ft.Colors.GREY_600, size=13,
            ),

            ft.Divider(),

            ft.Row([self.tf_busca], spacing=8),

            ft.Container(
                height=280,
                border=ft.border.all(1, ft.Colors.BLACK12),
                border_radius=10, bgcolor=ft.Colors.WHITE, padding=8,
                content=self.lista_contratos,
            ),

            self.painel_prazo,
        ])

        page.run_task(self._carregar)

    # ---- carregamento ----

    async def _carregar(self):
        self.loading.visible = True
        self.app_page.update()
        try:
            contratos = await asyncio.to_thread(get_contratos)
            clientes  = await asyncio.to_thread(get_clientes)
        except Exception as ex:
            print("Erro alertas_cadastro:", ex)
            contratos = clientes = []
        self.contratos    = contratos or []
        self.clientes_map = {c["id"]: c["nome"] for c in (clientes or [])}
        self.loading.visible = False
        self._filtrar()

    # ---- filtro ----

    def _filtrar(self, e=None):
        termo = (self.tf_busca.value or "").lower().strip()
        if termo:
            self.filtrados = [
                c for c in self.contratos
                if termo in str(c.get("nome", "")).lower()
                or termo in self.clientes_map.get(c.get("cliente_id"), "").lower()
                or termo in str(c.get("indice") or "").lower()
                or termo in str(c.get("responsavel") or "").lower()
            ]
        else:
            self.filtrados = list(self.contratos)
        self._render_lista()

    def _render_lista(self):
        self.lista_contratos.controls.clear()

        if not self.filtrados:
            self.lista_contratos.controls.append(
                ft.Text("Nenhum contrato encontrado.", color=ft.Colors.GREY_500,
                        italic=True, size=13))
            self.lista_contratos.update()
            return

        for c in self.filtrados[:40]:
            sel      = bool(self.selecionado and c["id"] == self.selecionado["id"])
            cli_nome = self.clientes_map.get(c.get("cliente_id"), "-")

            row = ft.Container(
                padding=ft.padding.symmetric(vertical=6, horizontal=10),
                border_radius=8,
                bgcolor=ft.Colors.BLUE_50 if sel else ft.Colors.GREY_50,
                border=ft.border.all(1, ft.Colors.BLUE_300 if sel else ft.Colors.GREY_200),
                content=ft.Row([
                    ft.Column([
                        ft.Text(c.get("nome", ""), weight=ft.FontWeight.W_500, size=13),
                        ft.Text(
                            f"{cli_nome}  •  Índice: {c.get('indice') or '-'}",
                            size=11, color=ft.Colors.GREY_600,
                        ),
                    ], spacing=2, expand=True),
                    ft.FilledTonalButton(
                        "+ Prazo", height=30,
                        on_click=lambda e, cc=c: self._selecionar(cc),
                    ),
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                on_click=lambda e, cc=c: self._selecionar(cc),
            )
            self.lista_contratos.controls.append(row)

        self.lista_contratos.update()

    # ---- selecionar contrato ----

    def _selecionar(self, contrato):
        self.selecionado = contrato
        self._render_lista()
        self._build_painel(contrato)

    def _build_painel(self, contrato):
        tid     = self.tenant_id
        tipos_p = []
        try:
            tipos_p = get_tipos_prazos_db(tid) or []
        except: pass

        tf_dt = ft.TextField(label="Data do prazo (DD/MM/AAAA)", width=200, read_only=True)
        tf_ob = ft.TextField(label="Observação", width=340)

        dd_tp = ft.Dropdown(
            label="Tipo de prazo", width=200,
            options=[ft.dropdown.Option(t["nome"]) for t in tipos_p],
            hint_text="Selecione..." if tipos_p else "Cadastre em Tipos",
        )

        tf_idx = ft.TextField(
            label="Índice do contrato",
            value=contrato.get("indice") or "",
            disabled=True, width=200,
        )

        def cal(e):
            calendario_ptbr(self.app_page, on_select=lambda d: (
                setattr(tf_dt, "value", d.strftime("%d/%m/%Y")),
                self.app_page.update(),
            ))

        lbl_err = ft.Text("", color=ft.Colors.RED_700, size=12)

        def salvar(e):
            if not tf_dt.value:
                lbl_err.value = "Selecione a data do prazo."
                self.app_page.update()
                return
            dt_db = data_br_para_db(tf_dt.value)
            if not dt_db:
                lbl_err.value = "Data inválida."
                self.app_page.update()
                return
            try:
                add_prazo(
                    contrato_id=contrato["id"],
                    meses=None,
                    observacao=tf_ob.value or "",
                    data_criacao=contrato.get("data_inicial"),
                    data_vencimento=dt_db,
                )
            except Exception as ex:
                lbl_err.value = f"Erro: {ex}"
                self.app_page.update()
                return

            # limpa campos após salvar
            tf_dt.value = ""
            tf_ob.value = ""
            dd_tp.value = None
            lbl_err.value = ""
            _snack(self.app_page, f"Prazo adicionado ao contrato {contrato.get('nome')}!")
            self.app_page.update()

        def cancelar(e):
            self.painel_prazo.visible = False
            self.selecionado = None
            self._render_lista()
            self.app_page.update()

        self.painel_prazo.content = ft.Container(
            padding=16, border_radius=12,
            bgcolor=ft.Colors.WHITE,
            border=ft.border.all(1, ft.Colors.BLUE_200),
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.ADD_ALARM, color=ft.Colors.BLUE_600),
                    ft.Text(
                        f"Novo prazo — {contrato.get('nome')}",
                        weight=ft.FontWeight.W_600, size=14,
                    ),
                ], spacing=8),

                ft.Divider(height=1),

                ft.Row([
                    ft.OutlinedButton("📅 Selecionar data", height=36, on_click=cal),
                    tf_dt,
                    dd_tp,
                ], spacing=10, wrap=True),

                ft.Row([tf_ob, tf_idx], spacing=10, wrap=True),

                lbl_err,

                ft.Row([
                    ft.FilledButton("Salvar prazo", on_click=salvar),
                    ft.TextButton("Cancelar", on_click=cancelar),
                ], spacing=12),
            ], spacing=10),
        )

        self.painel_prazo.visible = True
        self.app_page.update()


# ======================================================
# EXPORT
# ======================================================

def alertas_cadastro_view(page: ft.Page):
    return AlertasCadastroView(page)