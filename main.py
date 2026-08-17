import flet as ft
import asyncio
import time
import traceback
import uuid

import httpx

from pages.login.view import login_view
from pages import dashboard, clientes, contratos, relatorios, painel
from pages.admin.view import admin_view
from database.models import registrar_log
from database.supabase_client import new_session_client, run_db, supabase_admin, SessaoExpiradaError
from pages.partes.view import partes_view
from pages.tipos_partes.view import tipos_partes_view
from pages.alertas_cadastro.view import alertas_cadastro_view
from pages.cargos.view import cargos_view
from pages.logs.view import logs_view
from pages.erros.view import tela_404, tela_500, tela_conexao, tela_sessao_expirada
from app.layout import AppLayout
from utils.permissoes import pode, eh_administrador, algum_modulo_leitura, mensagem_sem_permissao


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

    session_id = uuid.uuid4().hex[:12]
    page.local_store["session_id"] = session_id
    inicio_sessao = time.monotonic()

    print(f"🔌 CONEXÃO [{session_id}] nova sessão iniciada")

    try:
        page.local_store["supabase_client"] = new_session_client()
    except Exception as ex:
        print(f"🔴 CRASH_INIT_SUPABASE [{session_id}]: {ex}")
        page.local_store["supabase_client"] = None

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

    def _log_sistema(acao: str, detalhes: str):
        tenant_id = page.local_store.get("tenant_id")
        usuario_id = page.local_store.get("usuario_id")
        print(f"⚡ SESSAO [{session_id}] {acao}: {detalhes}")
        if not (tenant_id and supabase_admin):
            return
        payload = {
            "usuario_id": usuario_id,
            "acao": acao,
            "detalhes": f"[sessao={session_id}] {detalhes}"[:2000],
            "tenant_id": tenant_id,
            "nivel": "sistema",
        }
        try:
            supabase_admin.table("logs").insert(payload).execute()
        except Exception as e:
            if "PGRST204" in str(e) or "nivel" in str(e):
                payload.pop("nivel", None)
                try:
                    supabase_admin.table("logs").insert(payload).execute()
                except Exception as e2:
                    print(f"❌ Falha ao gravar log de sistema ({acao}): {e2}")
            else:
                print(f"❌ Falha ao gravar log de sistema ({acao}): {e}")

    def _on_disconnect(e):
        duracao = time.monotonic() - inicio_sessao
        _log_sistema(
            "Sessão desconectada",
            f"duração={duracao:.0f}s usuario={page.local_store.get('usuario_nome') or '-'}",
        )

    def _on_error(e):
        detalhe = getattr(e, "data", None) or str(e)
        _log_sistema("Erro no cliente (frontend)", str(detalhe))
        try:
            page.snack_bar = ft.SnackBar(
                ft.Text("Ocorreu um problema inesperado nesta tela. Se persistir, atualize a página."),
                bgcolor=ft.Colors.RED_100,
            )
            page.snack_bar.open = True
            page.update()
        except Exception:
            pass

    page.on_disconnect = _on_disconnect
    page.on_error = _on_error

    def log_async(usuario_id, acao):
        tenant_id = page.local_store.get("tenant_id")

        async def run():
            try:
                await run_db(page, registrar_log, usuario_id, acao, tenant_id=tenant_id)
            except Exception:
                pass

        page.run_task(run)

    def get_view(route):
        try:
            return _get_view_interno(route)
        except SessaoExpiradaError:
            return tela_sessao_expirada(page)
        except httpx.TransportError as ex:
            print(f"🌐 FALHA_CONEXAO [{route}]: {ex}")
            return tela_conexao(page, route)
        except Exception as ex:
            tb = traceback.format_exc()
            print(f"🔴 CRASH_ROTA [{route}]:\n{tb}")
            _log_sistema(
                f"Crash ao renderizar rota {route}",
                f"{type(ex).__name__}: {ex}\n{tb[-1500:]}",
            )
            return tela_500(page, route)

    def _get_view_interno(route):

        usuario_id = page.local_store.get("usuario_id")

        if route != "/login" and not usuario_id:
            page.go("/login")
            return ft.Container()

        if route == "/login":
            if "login" not in views_cache:
                views_cache["login"] = login_view(page, page.go)
            return views_cache["login"]

        if route == "/dashboard":
            if usuario_id:
                log_async(usuario_id, "Acessou o Dashboard")
            return dashboard.dashboard_view(page)

        if route == "/clientes":
            if not pode(page, "clientes", "ler"):
                return mensagem_sem_permissao("visualizar", page)
            return clientes.clientes_view(page)

        if route == "/contratos":
            if not pode(page, "contratos", "ler"):
                return mensagem_sem_permissao("visualizar", page)
            return contratos.contratos_view(page)

        if route in ["/alertas", "/painel"]:
            if not pode(page, "prazos", "ler"):
                return mensagem_sem_permissao("visualizar", page)
            return painel.painel_view(page)

        if route == "/relatorios":
            if not algum_modulo_leitura(page):
                return mensagem_sem_permissao("visualizar", page)
            return relatorios.relatorios_view(page)

        if route == "/partes":
            if not pode(page, "partes", "ler"):
                return mensagem_sem_permissao("visualizar", page)
            return partes_view(page)

        if route == "/tipos-partes":
            if not pode(page, "categorias", "ler"):
                return mensagem_sem_permissao("visualizar", page)
            return tipos_partes_view(page)

        if route == "/alertas-cadastro":
            if not pode(page, "prazos", "ler"):
                return mensagem_sem_permissao("visualizar", page)
            return alertas_cadastro_view(page)

        if route == "/admin":
            if not eh_administrador(page):
                return mensagem_sem_permissao("acessar", page)
            return admin_view(page)

        if route == "/cargos":
            if not eh_administrador(page):
                return mensagem_sem_permissao("acessar", page)
            return cargos_view(page)

        if route == "/auditoria":
            if not eh_administrador(page):
                return mensagem_sem_permissao("acessar", page)
            return logs_view(page)

        return tela_404(page, route)

    try:
        layout = AppLayout(page, get_view)
        page.layout_instance = layout
    except Exception as ex:
        tb = traceback.format_exc()
        print(f"🔴 CRASH_INIT_LAYOUT [{session_id}]:\n{tb}")
        _log_sistema(
            "Crash ao inicializar o layout principal",
            f"{type(ex).__name__}: {ex}\n{tb[-1500:]}",
        )
        page.controls.clear()
        page.add(
            ft.Container(
                expand=True,
                alignment=ft.alignment.center,
                content=ft.Column(
                    [
                        ft.Icon(ft.Icons.ERROR_OUTLINE, size=52, color=ft.Colors.RED_300),
                        ft.Text(
                            "Não foi possível iniciar o sistema.",
                            size=18, weight=ft.FontWeight.BOLD,
                            text_align=ft.TextAlign.CENTER,
                        ),
                        ft.Text(
                            "Tente recarregar a página. Se o problema persistir, "
                            "contate o suporte.",
                            size=13, color=ft.Colors.GREY_600,
                            text_align=ft.TextAlign.CENTER,
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=10,
                ),
            )
        )
        page.update()
        return

    def on_route_change(e):
        print("➡️ ROTA:", page.route)

        try:
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

        except SessaoExpiradaError:
            pass

        except httpx.TransportError as ex:
            print(f"🌐 FALHA_CONEXAO_NAVEGACAO [{page.route}]: {ex}")
            try:
                page.controls.clear()
                page.add(tela_conexao(page, page.route))
                page.update()
            except Exception:
                pass

        except Exception as ex:
            tb = traceback.format_exc()
            print(f"🔴 CRASH_NAVIGATE [{page.route}]:\n{tb}")
            _log_sistema(
                f"Crash ao navegar para {page.route}",
                f"{type(ex).__name__}: {ex}\n{tb[-1500:]}",
            )
            try:
                page.controls.clear()
                page.add(tela_500(page, page.route))
                page.update()
            except Exception:
                pass

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