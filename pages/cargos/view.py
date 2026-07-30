"""
pages/cargos/view.py

Tela de Administração > Cargos e Permissões.
Só acessível a Administradores (ver utils/permissoes.eh_administrador).

Permite:
  - Ver os 3 cargos padrão (Leitor, Executor, Administrador) e
    quaisquer cargos customizados criados pelo tenant.
  - Criar um cargo novo.
  - Renomear ou excluir cargos não-padrão.
  - Marcar, por módulo, o que cada cargo pode: Ler / Cadastrar / Editar.
"""

import flet as ft

from database.models import (
    get_cargos,
    get_cargo_permissoes,
    add_cargo,
    update_cargo_nome,
    delete_cargo,
    set_permissao_cargo,
    MODULOS_PERMISSAO,
)
from database.supabase_client import run_db
from utils.log_acao import log_acao


NOMES_MODULO = {
    "clientes": "Clientes",
    "contratos": "Contratos",
    "categorias": "Categorias",
    "prazos": "Prazos",
    "partes": "Partes",
}


def _snack(page: ft.Page, msg: str):
    page.snack_bar = ft.SnackBar(ft.Text(msg))
    page.snack_bar.open = True
    page.update()


class CargosView(ft.Column):

    def __init__(self, page: ft.Page):
        super().__init__(expand=True, spacing=16, scroll=ft.ScrollMode.AUTO)

        self.app_page = page
        self.tenant_id = page.local_store.get("tenant_id")

        self.loading = ft.ProgressRing(width=20, height=20, stroke_width=2, visible=False)
        self.lista_cargos = ft.Column(spacing=12)

        self.tf_novo_cargo = ft.TextField(
            label="Nome do novo cargo", width=260, dense=True,
        )

        self.controls = [
            ft.Row([
                ft.Text("Cargos e Permissões", size=22, weight=ft.FontWeight.BOLD),
                self.loading,
            ], spacing=10),
            ft.Text(
                "Cada cargo define o que seus usuários podem fazer em cada módulo. "
                "Um usuário tem sempre exatamente 1 cargo (ver tela de Administração).",
                size=12, color=ft.Colors.GREY_600,
            ),
            ft.Container(
                padding=14, border_radius=10, bgcolor=ft.Colors.WHITE,
                border=ft.border.all(1, ft.Colors.GREY_200),
                content=ft.Row(
                    [
                        self.tf_novo_cargo,
                        ft.FilledButton(
                            "Criar cargo",
                            icon=ft.Icons.ADD,
                            on_click=lambda e: self.app_page.run_task(self._criar_cargo),
                        ),
                    ],
                    spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ),
            self.lista_cargos,
        ]

        page.run_task(self._carregar)

    # ══════════════════════════════════════════════════════
    # CARGA
    # ══════════════════════════════════════════════════════

    async def _carregar(self):
        self.loading.visible = True
        self.app_page.update()

        try:
            cargos = await run_db(self.app_page, get_cargos, self.tenant_id) or []
        except Exception as ex:
            print("❌ Erro ao carregar cargos:", ex)
            cargos = []
            _snack(self.app_page, "Não foi possível carregar os cargos. Tente novamente.")

        self.lista_cargos.controls.clear()

        if not cargos:
            self.lista_cargos.controls.append(
                ft.Text("Nenhum cargo cadastrado ainda.", color=ft.Colors.GREY_500, italic=True)
            )
        else:
            for cargo in cargos:
                self.lista_cargos.controls.append(await self._card_cargo(cargo))

        self.loading.visible = False
        self.app_page.update()

    async def _card_cargo(self, cargo: dict) -> ft.Container:
        cargo_id = cargo["id"]
        padrao = bool(cargo.get("padrao"))

        try:
            permissoes = await run_db(self.app_page, get_cargo_permissoes, cargo_id) or {}
        except Exception as ex:
            print(f"❌ Erro ao carregar permissões do cargo {cargo_id}:", ex)
            permissoes = {}
            _snack(self.app_page, f"Erro ao carregar permissões de '{cargo.get('nome')}'.")

        tf_nome = ft.TextField(
            value=cargo.get("nome", ""), width=220, dense=True,
            read_only=padrao,  # nome dos 3 cargos-base não muda
        )

        linhas_modulo = []
        for modulo in MODULOS_PERMISSAO:
            perm = permissoes.get(modulo, {"pode_ler": False, "pode_cadastrar": False, "pode_editar": False})

            cb_ler = ft.Checkbox(value=perm["pode_ler"], label="Ler")
            cb_cad = ft.Checkbox(value=perm["pode_cadastrar"], label="Cadastrar")
            cb_edt = ft.Checkbox(value=perm["pode_editar"], label="Editar")

            async def _salvar_permissao(e, m=modulo, ler=cb_ler, cad=cb_cad, edt=cb_edt):
                # cadastrar/editar sem ler não faz sentido — mesma regra
                # aplicada no backend (set_permissao_cargo), refletida
                # aqui visualmente também.
                if (cad.value or edt.value) and not ler.value:
                    ler.value = True
                    self.app_page.update()

                try:
                    resultado = await run_db(
                        self.app_page, set_permissao_cargo,
                        cargo_id, m, ler.value, cad.value, edt.value,
                    )
                except Exception as ex:
                    _snack(self.app_page, f"Erro de conexão ao salvar permissão: {ex}")
                    return

                if isinstance(resultado, dict) and resultado.get("_error"):
                    _snack(self.app_page, f"Erro ao salvar permissão: {resultado['_error']}")
                    return

                _snack(self.app_page, f"'{NOMES_MODULO[m]}' atualizado para '{cargo.get('nome')}'.")
                log_acao(
                    self.app_page,
                    f"Permissão alterada no cargo '{cargo.get('nome')}'",
                    f"módulo={m} ler={ler.value} cadastrar={cad.value} editar={edt.value}",
                )

            for cb in (cb_ler, cb_cad, cb_edt):
                cb.on_change = _salvar_permissao

            linhas_modulo.append(
                ft.Row(
                    [
                        ft.Container(ft.Text(NOMES_MODULO[modulo], size=13, weight=ft.FontWeight.W_600), width=110),
                        cb_ler, cb_cad, cb_edt,
                    ],
                    spacing=4,
                )
            )

        async def _salvar_nome(e):
            novo = (tf_nome.value or "").strip()
            if not novo:
                _snack(self.app_page, "O nome do cargo não pode ficar vazio.")
                tf_nome.value = cargo.get("nome", "")
                self.app_page.update()
                return
            if novo == cargo.get("nome"):
                return
            try:
                resultado = await run_db(self.app_page, update_cargo_nome, cargo_id, novo)
            except Exception as ex:
                _snack(self.app_page, f"Erro de conexão ao renomear: {ex}")
                return
            if isinstance(resultado, dict) and resultado.get("_error"):
                _snack(self.app_page, resultado["_error"])
                tf_nome.value = cargo.get("nome", "")
                self.app_page.update()
                return
            nome_anterior = cargo.get("nome")
            cargo["nome"] = novo
            _snack(self.app_page, "Cargo renomeado.")
            log_acao(self.app_page, f"Cargo renomeado: '{nome_anterior}' → '{novo}'")

        tf_nome.on_blur = _salvar_nome

        async def _excluir(e):
            try:
                resultado = await run_db(self.app_page, delete_cargo, cargo_id)
            except Exception as ex:
                _snack(self.app_page, f"Erro de conexão ao excluir: {ex}")
                return
            if isinstance(resultado, dict) and resultado.get("_error"):
                _snack(self.app_page, resultado["_error"])
                return
            _snack(self.app_page, f"Cargo '{cargo.get('nome')}' excluído.")
            log_acao(self.app_page, f"Cargo excluído: '{cargo.get('nome')}'")
            self.app_page.run_task(self._carregar)

        def _confirmar_exclusao(e):
            dlg = ft.AlertDialog(
                modal=True,
                title=ft.Text("Excluir cargo"),
                content=ft.Text(
                    f"Tem certeza que deseja excluir o cargo '{cargo.get('nome')}'? "
                    "Essa ação não pode ser desfeita."
                ),
                actions=[
                    ft.TextButton("Cancelar", on_click=lambda e: self._fechar_dialog(dlg)),
                    ft.FilledButton(
                        "Excluir",
                        style=ft.ButtonStyle(bgcolor=ft.Colors.RED),
                        on_click=lambda e: (self._fechar_dialog(dlg), self.app_page.run_task(_excluir, e)),
                    ),
                ],
            )
            self.app_page.overlay.append(dlg)
            dlg.open = True
            self.app_page.update()

        return ft.Container(
            padding=16, border_radius=10, bgcolor=ft.Colors.WHITE,
            border=ft.border.all(1, ft.Colors.GREY_200),
            content=ft.Column(
                [
                    ft.Row(
                        [
                            tf_nome,
                            ft.Container(
                                content=ft.Text("Padrão", size=11, color=ft.Colors.BLUE_700),
                                padding=ft.padding.symmetric(horizontal=8, vertical=2),
                                bgcolor=ft.Colors.BLUE_50, border_radius=6,
                                visible=padrao,
                            ),
                            ft.Container(expand=True),
                            ft.IconButton(
                                icon=ft.Icons.DELETE_OUTLINE,
                                icon_color=ft.Colors.RED_400,
                                tooltip="Excluir cargo" if not padrao else "Cargos padrão não podem ser excluídos",
                                disabled=padrao,
                                on_click=_confirmar_exclusao,
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Divider(height=1),
                    ft.Column(linhas_modulo, spacing=6),
                ],
                spacing=10,
            ),
        )

    def _fechar_dialog(self, dlg):
        dlg.open = False
        self.app_page.update()

    # ══════════════════════════════════════════════════════
    # CRIAR CARGO
    # ══════════════════════════════════════════════════════

    async def _criar_cargo(self):
        nome = (self.tf_novo_cargo.value or "").strip()
        if not nome:
            _snack(self.app_page, "Digite um nome para o novo cargo.")
            return

        try:
            resultado = await run_db(self.app_page, add_cargo, self.tenant_id, nome)
        except Exception as ex:
            _snack(self.app_page, f"Erro de conexão ao criar cargo: {ex}")
            return

        if isinstance(resultado, dict) and resultado.get("_error"):
            _snack(self.app_page, resultado["_error"])
            return

        self.tf_novo_cargo.value = ""
        _snack(self.app_page, f"Cargo '{nome}' criado. Agora defina as permissões dele abaixo.")
        log_acao(self.app_page, f"Cargo criado: '{nome}'")
        await self._carregar()


def cargos_view(page: ft.Page):
    return CargosView(page)