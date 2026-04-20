import flet as ft
import threading

from pages.login.view import login_view
from pages import dashboard, clientes, contratos, relatorios, painel
from pages.admin.view import admin_view  # ✅ AQUI
from database.models import registrar_log
from pages.partes.view import partes_view
from pages.tipos_partes.view import tipos_partes_view
from app.layout import AppLayout


# =========================
# HELPERS
# =========================
def _as_bool(v) -> bool:
    """Normaliza bool vindo do Supabase/local_store (bool/int/str)."""
    if isinstance(v, bool):
        return v
    if isinstance(v, int):
        return v == 1
    if isinstance(v, str):
        return v.strip().lower() in ("true", "t", "1", "yes", "y", "sim")
    return False


# =========================
# APP PRINCIPAL
# =========================
def main(page: ft.Page):

    # =========================
    # CONFIG GERAL
    # =========================
    page.title = "DocsFlow System"
    page.theme_mode = "light"
    page.bgcolor = ft.Colors.GREY_50
    page.window_width = 1200
    page.window_height = 720
    page.padding = 0

    # sessão simples
    page.local_store = {}

    # =========================
    # CACHE DE TELAS
    # =========================
    views_cache = {}

    # =========================
    # LOG EM BACKGROUND
    # =========================
    def log_async(usuario_id, acao):

        def run():
            try:
                registrar_log(usuario_id, acao)
            except:
                pass

        threading.Thread(
            target=run,
            daemon=True
        ).start()

    # =========================
    # ROTAS → TELAS
    # =========================
    def get_view(route: str):

        usuario_id = page.local_store.get("usuario_id")

        # Proteção: sem login
        if route != "/login" and not usuario_id:
            page.go("/login")
            return ft.Container()

        # ================= LOGIN =================
        if route == "/login":

            if "login" not in views_cache:
                views_cache["login"] = login_view(page, page.go)

            return views_cache["login"]

        # ================= DASHBOARD =================
        if route == "/dashboard":

            if usuario_id:
                log_async(usuario_id, "Acessou o Dashboard")

            if route not in views_cache:
                views_cache[route] = dashboard.dashboard_view(page)

            return views_cache[route]

        # ================= CLIENTES =================
        if route == "/clientes":

            if route not in views_cache:
                views_cache[route] = clientes.clientes_view(page)

            return views_cache[route]

        # ================= CONTRATOS =================
        if route == "/contratos":

            if route not in views_cache:
                views_cache[route] = contratos.contratos_view(page)

            return views_cache[route]

        # ================= ALERTAS =================
        if route in ["/alertas", "/painel"]:

            if "/alertas" not in views_cache:
                views_cache["/alertas"] = painel.painel_view(page)

            return views_cache["/alertas"]

        # ================= RELATÓRIOS =================
        if route == "/relatorios":

            if route not in views_cache:
                views_cache[route] = relatorios.relatorios_view(page)

            return views_cache[route]

        # ================= PARTES =================
        if route == "/partes":
            if route not in views_cache:
                views_cache[route] = partes_view(page)
            return views_cache[route]

        # ================= TIPOS DE PARTES =================
        if route == "/tipos-partes":
            if route not in views_cache:
                views_cache[route] = tipos_partes_view(page)
            return views_cache[route]

        # ================= ADMIN =================
        if route == "/admin":

            # Pode mostrar no menu pra todos, mas bloqueia aqui
            is_admin = _as_bool(page.local_store.get("is_admin"))
            is_global_admin = _as_bool(page.local_store.get("is_global_admin"))

            # DEBUG opcional (descomente se quiser ver no console):
            # print("DEBUG ADMIN local_store:", page.local_store)

            if not (is_admin or is_global_admin):
                return ft.Container(
                    expand=True,
                    padding=24,
                    content=ft.Column(
                        [
                            ft.Text("Acesso negado", size=18, weight=ft.FontWeight.BOLD),
                            ft.Text("Essa área é exclusiva para administradores."),
                        ],
                        spacing=8,
                    )
                )

            if route not in views_cache:
                views_cache[route] = admin_view(page)

            return views_cache[route]

        # fallback seguro
        return get_view("/dashboard")

    # =========================
    # LAYOUT PRINCIPAL
    # =========================
    layout = AppLayout(page, get_view)

    # =========================
    # EVENTO DE ROTA
    # =========================
    def on_route_change(e):

        # LOGIN → sem layout
        if page.route == "/login":
            page.controls.clear()
            page.add(get_view("/login"))
            page.update()
            return

        # OUTRAS TELAS → layout único
        if layout not in page.controls:
            page.controls.clear()
            page.add(layout)

        layout.navigate(page.route)
        page.update()

    page.on_route_change = on_route_change

    # =========================
    # START
    # =========================
    page.go("/login")


# =========================
# EXECUÇÃO
# =========================
if __name__ == "__main__":

    import os

    port = int(os.environ.get("PORT", 10000))

    print(f"🚀 Servidor iniciado na porta {port}")

    import os as _os
    upload_dir = _os.environ.get("FLET_UPLOAD_DIR", "/tmp/flet_uploads")
    _os.makedirs(upload_dir, exist_ok=True)

    ft.app(
        target=main,
        port=port,
        upload_dir=upload_dir,
        assets_dir="images"
    )