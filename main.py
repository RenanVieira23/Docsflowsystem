import flet as ft
import threading

from pages.login.view import login_view
from pages import dashboard, clientes, contratos, relatorios, painel
from database.models import registrar_log

from app.layout import AppLayout


# =========================
# APP PRINCIPAL
# =========================
def main(page: ft.Page):

    # =========================
    # CONFIG GERAL
    # =========================
    page.title = "Sistema Jurídico Heringer"
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

    PORTA_FIXA = 8550

    print(f"🚀 Servidor iniciado em http://localhost:{PORTA_FIXA}")

    ft.run(
        main,
        view=ft.AppView.WEB_BROWSER,
        port=PORTA_FIXA,
    )