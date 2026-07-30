import flet as ft
import asyncio

from database.models import (
    get_usuarios_do_tenant,
    get_usuarios,
    delete_usuario_admin,
    get_cargos,
)
from database.supabase_client import run_db
from pages.admin.form import criar_usuario_dialog, editar_usuario_dialog
from utils.log_acao import log_acao


# ======================================================
# VIEW
# ======================================================

class AdminView(ft.Column):

    def __init__(self, page: ft.Page):
        super().__init__(expand=True, spacing=10)

        self.app_page = page
        self.usuarios = []
        self.cargos = []   # carregado junto com os usuários, usado no dropdown de cada linha

        # Tenant do admin logado
        self.tenant_id = page.local_store.get("tenant_id")
        self.is_global_admin = page.local_store.get("is_global_admin", False)

        # =========================
        # LOADING
        # =========================
        self.loading = ft.ProgressRing(
            visible=False, width=20, height=20, stroke_width=2
        )

        # =========================
        # TABELA
        # =========================
        self.tabela = ft.DataTable(
            column_spacing=16,
            heading_row_height=38,
            data_row_min_height=36,
            divider_thickness=0.5,
            columns=[
                ft.DataColumn(ft.Text("ID")),
                ft.DataColumn(ft.Text("Nome (usuário)")),
                ft.DataColumn(ft.Text("E-mail")),
                ft.DataColumn(ft.Text("Cargo")),
                ft.DataColumn(ft.Text("Admin")),
                ft.DataColumn(ft.Text("Ações")),
            ],
            rows=[],
        )

        self.aviso_sem_cargos = ft.Container(
            padding=12, border_radius=8, bgcolor=ft.Colors.AMBER_50,
            border=ft.border.all(1, ft.Colors.AMBER_200),
            visible=False,
            content=ft.Row([
                ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color=ft.Colors.AMBER_700, size=18),
                ft.Text(
                    "Nenhum cargo cadastrado ainda para este tenant. "
                    "Vá em 'Cargos e Permissões' no menu para criar/conferir os cargos "
                    "antes de vinculá-los aos usuários.",
                    size=12, color=ft.Colors.AMBER_900,
                ),
            ], spacing=8),
        )

        # =========================
        # LAYOUT
        # =========================
        self.controls.extend([

            ft.Row(
                [
                    ft.Text("Gestão de Usuários", size=22, weight=ft.FontWeight.BOLD),
                    ft.Row(
                        [
                            ft.FilledButton(
                                "Novo Usuário",
                                icon=ft.Icons.PERSON_ADD,
                                height=36,
                                on_click=self.abrir_criar,
                            ),
                            ft.OutlinedButton(
                                "Atualizar",
                                height=36,
                                on_click=self.recarregar,
                            ),
                            self.loading,
                        ],
                        spacing=8,
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),

            ft.Text(
                "Gerencie os usuários do sistema e o cargo de cada um. "
                "Somente administradores têm acesso a esta tela.",
                color=ft.Colors.GREY_600,
                size=13,
            ),

            self.aviso_sem_cargos,

            ft.Divider(),

            ft.Container(
                expand=True,
                content=ft.Column(
                    [self.tabela],
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
            if self.tenant_id:
                dados = await run_db(
                    self.app_page, get_usuarios_do_tenant, self.tenant_id
                )
            else:
                dados = await run_db(self.app_page, get_usuarios)
        except Exception as ex:
            print("Erro admin usuários:", ex)
            dados = []
            self._snack("Não foi possível carregar os usuários. Tente novamente.")

        try:
            self.cargos = await run_db(self.app_page, get_cargos, self.tenant_id) or []
        except Exception as ex:
            print("Erro admin cargos:", ex)
            self.cargos = []
            self._snack("Não foi possível carregar a lista de cargos.")

        self.usuarios = dados or []
        self.aviso_sem_cargos.visible = not self.cargos
        self.loading.visible = False
        self._renderizar_tabela()

    def recarregar(self, e=None):
        self.app_page.run_task(self._carregar)

    # ======================================================
    # TABELA
    # ======================================================

    def _renderizar_tabela(self):
        self.tabela.rows.clear()

        usuario_logado_id = self.app_page.local_store.get("usuario_id")

        for u in self.usuarios:

            eh_voce = u.get("id") == usuario_logado_id

            badge_admin = ft.Icon(
                ft.Icons.VERIFIED,
                size=16,
                color=ft.Colors.AMBER_600,
                tooltip="Admin",
            ) if u.get("is_admin") else ft.Text("-", color=ft.Colors.GREY_400)

            # A lista só EXIBE o cargo (texto simples). A troca de cargo
            # acontece exclusivamente pelo diálogo "Editar" — evita
            # alterações acidentais direto na tabela e mantém um único
            # lugar de validação (mesmo fluxo do cadastro de usuário).
            cargo_atual = next(
                (c for c in self.cargos if c["id"] == u.get("cargo_id")), None
            )
            texto_cargo = ft.Text(
                cargo_atual["nome"] if cargo_atual else "Sem cargo",
                color=ft.Colors.GREY_800 if cargo_atual else ft.Colors.RED_400,
                italic=not cargo_atual,
            )

            botoes = [
                ft.TextButton(
                    "Editar",
                    on_click=lambda e, uu=u: self.editar(uu),
                ),
            ]

            # Não deixa deletar a si mesmo
            if not eh_voce:
                botoes.append(
                    ft.TextButton(
                        "Excluir",
                        style=ft.ButtonStyle(color=ft.Colors.RED),
                        on_click=lambda e, uu=u: self.confirmar_exclusao(uu),
                    )
                )
            else:
                botoes.append(
                    ft.Text("(você)", color=ft.Colors.GREY_400, size=12)
                )

            self.tabela.rows.append(
                ft.DataRow(cells=[
                    ft.DataCell(ft.Text(str(u.get("id", "")))),
                    ft.DataCell(ft.Text(u.get("usuario", ""), weight=ft.FontWeight.W_500)),
                    ft.DataCell(ft.Text(u.get("email") or "-", size=12)),
                    ft.DataCell(texto_cargo),
                    ft.DataCell(badge_admin),
                    ft.DataCell(ft.Row(botoes, spacing=4)),
                ])
            )

        self.tabela.update()

    def _snack(self, msg: str):
        self.app_page.snack_bar = ft.SnackBar(ft.Text(msg))
        self.app_page.snack_bar.open = True
        self.app_page.update()

    # ======================================================
    # CRUD
    # ======================================================

    def abrir_criar(self, e):
        dialog = criar_usuario_dialog(
            self.app_page,
            tenant_id=self.tenant_id,
            on_save=self.recarregar,
        )
        self.app_page.overlay.append(dialog)
        dialog.open = True
        self.app_page.update()

    def editar(self, usuario):
        dialog = editar_usuario_dialog(
            self.app_page,
            usuario=usuario,
            on_save=self.recarregar,
        )
        self.app_page.overlay.append(dialog)
        dialog.open = True
        self.app_page.update()

    def confirmar_exclusao(self, usuario):
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Confirmar exclusão"),
            content=ft.Text(
                f"Excluir o usuário '{usuario.get('usuario')}'?\n\n"
                "Esta ação remove o acesso ao sistema permanentemente."
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: self._fechar(dialog)),
                ft.FilledButton(
                    "Excluir",
                    style=ft.ButtonStyle(bgcolor=ft.Colors.RED),
                    on_click=lambda e: self.app_page.run_task(self._excluir, usuario, dialog),
                ),
            ],
        )
        self.app_page.overlay.append(dialog)
        dialog.open = True
        self.app_page.update()

    async def _excluir(self, usuario, dialog):
        try:
            ok = await run_db(self.app_page, delete_usuario_admin, usuario["id"])
        except Exception as ex:
            dialog.open = False
            self._snack(f"Erro de conexão ao excluir: {ex}")
            return

        dialog.open = False

        msg = (
            f"Usuário '{usuario['usuario']}' excluído."
            if ok else
            "Erro ao excluir usuário."
        )
        self._snack(msg)
        if ok:
            log_acao(self.app_page, f"Usuário excluído: '{usuario['usuario']}'", f"usuario_id={usuario['id']}")
        self.recarregar()

    def _fechar(self, dialog):
        dialog.open = False
        self.app_page.update()


# ======================================================
# EXPORT
# ======================================================

def admin_view(page: ft.Page) -> ft.Control:
    # Proteção extra: só admin acessa
    if not page.local_store.get("is_admin") and not page.local_store.get("is_global_admin"):
        return ft.Container(
            expand=True,
            alignment=ft.alignment.center,
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.LOCK_OUTLINE, size=48, color=ft.Colors.GREY_400),
                    ft.Text(
                        "Acesso restrito a administradores.",
                        color=ft.Colors.GREY_600,
                        size=16,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=12,
            ),
        )

    return AdminView(page)