import flet as ft
import asyncio

from pages.login.view import login_view
from pages import dashboard, clientes, contratos, relatorios, painel
from pages.admin.view import admin_view
from database.models import registrar_log
from database.supabase_client import new_session_client, run_db
from pages.partes.view import partes_view
from pages.tipos_partes.view import tipos_partes_view
from pages.alertas_cadastro.view import alertas_cadastro_view
from app.layout import AppLayout


def _as_bool(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, int):
        return v == 1
    if isinstance(v, str):
        return v.lower() in ("true", "1", "sim")
    return False


def main(page: ft.Page):

    page.local_store = {}

    # =========================================================
    # FIX MULTI-SESSÃO: cria um client Supabase isolado para
    # ESTA sessão específica e guarda em page.local_store, que
    # é único por sessão/conexão. Esse client é passado
    # explicitamente a cada consulta via run_db() (ver models.py
    # e as páginas), garantindo que o token de autenticação de
    # um usuário NUNCA seja usado nas consultas de outro usuário.
    # =========================================================
    page.local_store["supabase_client"] = new_session_client()

    page.title = "DocsFlow System"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = ft.Colors.GREY_50
    page.padding = 0
    page.window_width = 1200
    page.window_height = 720

    views_cache = {}

    from app.filepicker import FilePickerService
    fp_service = FilePickerService()
    fp_service.register(page)

    print("✅ FilePicker Service ativo")

    # =========================================================
    # FIX RLS: log_async agora passa tenant_id para registrar_log
    # e roda via asyncio.to_thread (propaga o contexto da sessão
    # corretamente e evita threads soltas sem controle).
    # =========================================================
    def log_async(usuario_id, acao):
        tenant_id = page.local_store.get("tenant_id")

        async def run():
            try:
                await run_db(page, registrar_log, usuario_id, acao, tenant_id=tenant_id)
            except Exception:
                pass

        page.run_task(run)

    def get_view(route):

        usuario_id = page.local_store.get("usuario_id")

        if route != "/login" and not usuario_id:
            page.go("/login")
            return ft.Container()

        if route == "/login":
            # login não muda entre visitas, esse pode continuar em cache
            if "login" not in views_cache:
                views_cache["login"] = login_view(page, page.go)
            return views_cache["login"]

        # =========================================================
        # FIX: as telas abaixo eram guardadas em views_cache e NUNCA
        # reconstruídas — então dados criados/alterados em outra tela
        # (ex: um novo contrato) só apareciam aqui na PRIMEIRA vez que
        # a tela era aberta na sessão; visitas seguintes reexibiam a
        # mesma instância antiga, com os dados de quando foi criada.
        # Agora cada navegação cria a tela de novo, sempre com dados
        # atuais. O custo (reconstruir + buscar dados de novo) é
        # pequeno, já que essas buscas rodam em paralelo.
        # =========================================================

        if route == "/dashboard":
            if usuario_id:
                log_async(usuario_id, "Acessou o Dashboard")
            return dashboard.dashboard_view(page)

        if route == "/clientes":
            return clientes.clientes_view(page)

        if route == "/contratos":
            return contratos.contratos_view(page)

        if route in ["/alertas", "/painel"]:
            return painel.painel_view(page)

        if route == "/relatorios":
            return relatorios.relatorios_view(page)

        if route == "/partes":
            return partes_view(page)

        if route == "/tipos-partes":
            return tipos_partes_view(page)

        if route == "/alertas-cadastro":
            return alertas_cadastro_view(page)

        if route == "/admin":
            is_admin = _as_bool(page.local_store.get("is_admin"))
            is_global_admin = _as_bool(page.local_store.get("is_global_admin"))

            if not (is_admin or is_global_admin):
                return ft.Container(
                    expand=True,
                    padding=24,
                    content=ft.Text("Acesso negado"),
                )

            return admin_view(page)

        page.go("/dashboard")
        return ft.Container()

    layout = AppLayout(page, get_view)
    page.layout_instance = layout

    def on_route_change(e):
        print("➡️ ROTA:", page.route)

        if page.route == "/login":
            page.controls.clear()
            page.add(get_view("/login"))
            page.update()
            return

        if layout not in page.controls:
            page.controls.clear()
            page.add(layout)

        layout.navigate(page.route)
        page.update()

    page.on_route_change = on_route_change

    if page.route == "":
        page.go("/login")
    else:
        on_route_change(None)


if __name__ == "__main__":
    import os

    port = int(os.environ.get("PORT", 5000))
    print(f"🚀 Servidor iniciado na porta {port}")

    upload_dir = os.environ.get("FLET_UPLOAD_DIR", "/tmp/flet_uploads")
    os.makedirs(upload_dir, exist_ok=True)

    ft.run(
        main,
        port=port,
        upload_dir=upload_dir,
        view=ft.AppView.WEB_BROWSER,
    )