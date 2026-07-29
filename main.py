import flet as ft
import asyncio
import time
import traceback
import uuid

from pages.login.view import login_view
from pages import dashboard, clientes, contratos, relatorios, painel
from pages.admin.view import admin_view
from database.models import registrar_log
from database.supabase_client import new_session_client, run_db, supabase_admin
from pages.partes.view import partes_view
from pages.tipos_partes.view import tipos_partes_view
from pages.alertas_cadastro.view import alertas_cadastro_view
from pages.cargos.view import cargos_view
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

    # Identificador único desta sessão/conexão específica — usado para
    # correlacionar, no log, tudo que aconteceu numa mesma sessão do
    # navegador (conexão, ações, erros, desconexão), mesmo antes do
    # login (quando ainda não há usuario_id).
    session_id = uuid.uuid4().hex[:12]
    page.local_store["session_id"] = session_id
    inicio_sessao = time.monotonic()

    print(f"🔌 CONEXÃO [{session_id}] nova sessão iniciada")

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
    # DIAGNÓSTICO: desconexão do navegador ("sumiu do nada") e
    # erros não tratados no lado do cliente. Isso é justamente o
    # tipo de evento que hoje passa em branco — o usuário vê a
    # tela travar/sumir e não sobra rastro nenhum pra investigar.
    # Usa supabase_admin diretamente (não run_db/client de sessão):
    # se o PROBLEMA é a conexão/sessão, um log que dependesse dela
    # também poderia falhar — o registro do problema não pode
    # depender da própria coisa que está com problema.
    # =========================================================

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
                # Migração sql/2026-07_logs_nivel.sql ainda não rodada
                # no Supabase — grava sem a coluna nova por enquanto.
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

    page.on_disconnect = _on_disconnect
    page.on_error = _on_error

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
        """
        Wrapper de segurança: se a construção de QUALQUER tela lançar
        uma exceção não tratada (ex: erro inesperado do Flet, dado
        vindo em formato que a tela não esperava, timeout de rede no
        meio da montagem), isso ANTES deixava a tela em branco/travada
        sem nenhum rastro — exatamente o tipo de sintoma relatado como
        "os contratos sumiram". Agora o erro é logado com o traceback
        completo (console + banco) e o usuário vê uma tela de erro
        clara, com botão para tentar de novo, em vez de tela vazia.
        """
        try:
            return _get_view_interno(route)
        except Exception as ex:
            tb = traceback.format_exc()
            print(f"🔴 CRASH_ROTA [{route}]:\n{tb}")
            _log_sistema(
                f"Crash ao renderizar rota {route}",
                f"{type(ex).__name__}: {ex}\n{tb[-1500:]}",
            )
            return _tela_erro_generico(route)

    def _tela_erro_generico(route):
        def _tentar_de_novo(e):
            page.go(route)

        return ft.Container(
            expand=True,
            alignment=ft.alignment.center,
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.ERROR_OUTLINE, size=48, color=ft.Colors.RED_300),
                    ft.Text("Algo deu errado ao carregar esta tela.", size=16),
                    ft.Text(
                        "O problema já foi registrado. Tente novamente — "
                        "se persistir, avise um administrador.",
                        size=13, color=ft.Colors.GREY_600,
                    ),
                    ft.FilledButton("Tentar novamente", on_click=_tentar_de_novo),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=10,
            ),
        )

    def _get_view_interno(route):

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
            if not pode(page, "clientes", "ler"):
                return mensagem_sem_permissao("visualizar")
            return clientes.clientes_view(page)

        if route == "/contratos":
            if not pode(page, "contratos", "ler"):
                return mensagem_sem_permissao("visualizar")
            return contratos.contratos_view(page)

        if route in ["/alertas", "/painel"]:
            if not pode(page, "prazos", "ler"):
                return mensagem_sem_permissao("visualizar")
            return painel.painel_view(page)

        if route == "/relatorios":
            if not algum_modulo_leitura(page):
                return mensagem_sem_permissao("visualizar")
            return relatorios.relatorios_view(page)

        if route == "/partes":
            if not pode(page, "partes", "ler"):
                return mensagem_sem_permissao("visualizar")
            return partes_view(page)

        if route == "/tipos-partes":
            if not pode(page, "categorias", "ler"):
                return mensagem_sem_permissao("visualizar")
            return tipos_partes_view(page)

        if route == "/alertas-cadastro":
            if not pode(page, "prazos", "ler"):
                return mensagem_sem_permissao("visualizar")
            return alertas_cadastro_view(page)

        if route == "/admin":
            if not eh_administrador(page):
                return mensagem_sem_permissao("acessar")
            return admin_view(page)

        if route == "/cargos":
            if not eh_administrador(page):
                return mensagem_sem_permissao("acessar")
            return cargos_view(page)

        page.go("/dashboard")
        return ft.Container()

    layout = AppLayout(page, get_view)
    page.layout_instance = layout

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
        except Exception as ex:
            # Mesma lógica do wrapper de get_view: navigate() também
            # pode falhar por motivos fora da tela em si (sidebar,
            # checagem de permissão, atualização do layout). Sem isso,
            # a exceção sobe até o loop de eventos do Flet e a sessão
            # trava/desconecta sem nenhum rastro — exatamente o tipo
            # de "sumiu do nada" relatado.
            tb = traceback.format_exc()
            print(f"🔴 CRASH_NAVIGATE [{page.route}]:\n{tb}")
            _log_sistema(
                f"Crash ao navegar para {page.route}",
                f"{type(ex).__name__}: {ex}\n{tb[-1500:]}",
            )
            try:
                page.controls.clear()
                page.add(_tela_erro_generico(page.route))
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