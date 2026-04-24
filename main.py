import flet as ft
import threading

from pages.login.view import login_view
from pages import dashboard, clientes, contratos, relatorios, painel
from pages.admin.view import admin_view
from database.models import registrar_log
from pages.partes.view import partes_view
from pages.tipos_partes.view import tipos_partes_view
from pages.alertas_cadastro.view import alertas_cadastro_view
from app.layout import AppLayout



# =========================
# HELPERS
# =========================
def _as_bool(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, int):
        return v == 1
    if isinstance(v, str):
        return v.lower() in ("true", "1", "sim")
    return False


# =========================
# APP
# =========================
def main(page: ft.Page):

    # CONFIG
    page.title = "DocsFlow System"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = ft.Colors.GREY_50
    page.padding = 0
    page.window_width = 1200
    page.window_height = 720

    page.local_store = {}
    views_cache = {}

    # =========================
    # FILE PICKER GLOBAL
    # =========================
    from app.filepicker import FilePickerService

    fp_service = FilePickerService()
    fp_service.register(page)

    print("✅ FilePicker Service ativo")
    # =========================
    # LOG ASYNC
    # =========================
    def log_async(usuario_id, acao):
        def run():
            try:
                registrar_log(usuario_id, acao)
            except:
                pass

        threading.Thread(target=run, daemon=True).start()

    # =========================
    # ROTAS
    # =========================
    def get_view(route):

        usuario_id = page.local_store.get("usuario_id")

        # 🔥 proteção login
        if route != "/login" and not usuario_id:
            page.go("/login")
            return ft.Container()

        # LOGIN
        if route == "/login":
            if "login" not in views_cache:
                views_cache["login"] = login_view(page, page.go)
            return views_cache["login"]

        # DASHBOARD
        if route == "/dashboard":

            if usuario_id:
                log_async(usuario_id, "Acessou o Dashboard")

            if route not in views_cache:
                views_cache[route] = dashboard.dashboard_view(page)

            return views_cache[route]

        # CLIENTES
        if route == "/clientes":
            if route not in views_cache:
                views_cache[route] = clientes.clientes_view(page)
            return views_cache[route]

        # CONTRATOS
        if route == "/contratos":
            if route not in views_cache:
                views_cache[route] = contratos.contratos_view(page)
            return views_cache[route]

        # ALERTAS
        if route in ["/alertas", "/painel"]:
            if "/alertas" not in views_cache:
                views_cache["/alertas"] = painel.painel_view(page)
            return views_cache["/alertas"]

        # RELATÓRIOS
        if route == "/relatorios":
            if route not in views_cache:
                views_cache[route] = relatorios.relatorios_view(page)
            return views_cache[route]

        # PARTES
        if route == "/partes":
            if route not in views_cache:
                views_cache[route] = partes_view(page)
            return views_cache[route]

        # TIPOS PARTES
        if route == "/tipos-partes":
            if route not in views_cache:
                views_cache[route] = tipos_partes_view(page)
            return views_cache[route]

        # ALERTAS CADASTRO
        if route == "/alertas-cadastro":
            if route not in views_cache:
                views_cache[route] = alertas_cadastro_view(page)
            return views_cache[route]

        # ADMIN
        if route == "/admin":

            is_admin = _as_bool(page.local_store.get("is_admin"))
            is_global_admin = _as_bool(page.local_store.get("is_global_admin"))

            if not (is_admin or is_global_admin):
                return ft.Container(
                    expand=True,
                    padding=24,
                    content=ft.Text("Acesso negado"),
                )

            if route not in views_cache:
                views_cache[route] = admin_view(page)

            return views_cache[route]

        # fallback
        page.go("/dashboard")
        return ft.Container()

    # =========================
    # LAYOUT
    # =========================
    layout = AppLayout(page, get_view)
    page.layout_instance = layout

    # =========================
    # ROUTE CHANGE
    # =========================
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

    # =========================
    # START (FLET 0.84 FIX)
    # =========================

    page.on_route_change = on_route_change

    # força rota inicial corretamente
    if page.route == "":
        page.go("/login")
    else:
        on_route_change(None)

# =========================
# RUN
# =========================
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