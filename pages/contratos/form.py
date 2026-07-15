"""
pages/contratos/form.py
========================
Diálogos de Novo / Editar / Ver contrato — multi-tenant.

Correções desta versão (definitiva):
  1. SEM url_target em qualquer botão (parâmetro inexistente no Flet 0.28/0.80).
     O parâmetro `url=` sozinho já abre em nova aba no Flet web.
  2. tenant_id obtido com fallback robusto: page.local_store -> page.session.
     Se ainda assim vier vazio, mostra erro amigável e não chama get_clientes().
  3. Anexos vindos DIRETO do Storage privado "Heringer" — sem tabela 'anexos'.
     Usa list_anexos_storage / upload_anexo_storage / delete_anexo_storage e
     get_anexo_signed_url (URL assinada com 1h de validade).
  4. FilePicker único por página, registrado no overlay UMA vez (get_filepicker).
  5. Validações de TextField.value blindadas contra None — sempre
     (value or "").isdigit() em vez de value.isdigit() (corrige datepicker).
  6. Handlers do calendário em funções nomeadas (em vez de
     lambda d: (setattr(...), recalcular(), page.update())) — mais legível
     e elimina cantos escuros do parser do lambda+tuple.
  7. Diálogos abrem com page.open() e fecham com page.close() (com fallback
     para a API antiga quando a versão do Flet não suportar).

FIXES v2:
  - _get_picker() removida: estava chamando get_filepicker() duas vezes e
    adicionando ao overlay novamente, causando "Unknown control: filepicker".
  - on_result: corrigido para ft.FilePickerResultEvent (era FilePickerUploadEvent).
  - picker.pick_files(): envolto em page.run_task() para evitar
    RuntimeWarning de coroutine não aguardada.
  - add_anexo removido de novo_contrato_dialog (Storage-only, sem tabela anexos)
    e removido o bloco duplicado que chamava add_anexo duas vezes.
"""

import flet as ft
import asyncio
import os
import time
from datetime import datetime
from dateutil.relativedelta import relativedelta

from database.supabase_client import run_db
from database.models import (
    add_contrato,
    update_contrato,
    add_prazo,
    update_prazo,
    get_clientes,
    get_contratos_por_cliente,
    get_prazos_por_contrato,
    get_partes,
    get_vinculos,
    get_contrato_partes,
    add_contrato_parte,
    delete_contrato_parte,
    # Storage privado "Heringer":
    list_anexos_storage,
    upload_anexo_storage,
    delete_anexo_storage,
    get_anexo_signed_url,
    get_tipos_contratos,
    get_tipos_prazos,
)

from utils.calendario_ptbr import calendario_ptbr
from utils.dataptbr import data_br_para_db, data_db_para_br, somar_meses


DB_FMT     = "%Y-%m-%d"
UPLOAD_DIR = os.environ.get("FLET_UPLOAD_DIR", "/tmp/flet_uploads")


# ======================================================
# HELPERS
# ======================================================

def _snack(page, msg):
    page.snack_bar = ft.SnackBar(ft.Text(msg))
    page.snack_bar.open = True
    page.update()




def _get_tenant(page):
    """Lê tenant_id de várias fontes possíveis (robustez contra None)."""
    tid = None
    try:
        if hasattr(page, "local_store") and page.local_store:
            tid = page.local_store.get("tenant_id")
    except Exception:
        tid = None
    if not tid:
        try:
            tid = page.session.get("tenant_id")
        except Exception:
            pass
    return tid


def _get_usuario_nome(page):
    try:
        if hasattr(page, "local_store") and page.local_store:
            return page.local_store.get("usuario_nome") or ""
    except Exception:
        pass
    try:
        return page.session.get("usuario_nome") or ""
    except Exception:
        return ""


def _is_int_str(s) -> bool:
    return bool((s or "").strip().isdigit())


def _parse_db(s):
    try:
        return datetime.strptime(s, DB_FMT)
    except Exception:
        return None


def _format_db(dt):
    return dt.strftime(DB_FMT) if dt else ""


def _calcular_meses(base, data):
    return (data.year - base.year) * 12 + (data.month - base.month)


def _data_por_meses(base, meses):
    return base + relativedelta(months=meses)


def _gerar_nome(sigla, contratos):
    mx = 0
    for c in (contratos or []):
        n = (c.get("nome") or "").strip()
        if n.startswith(sigla):
            suf = n[len(sigla):]
            if suf.isdigit():
                mx = max(mx, int(suf))
    return f"{sigla}{mx + 1:04d}"


def _icone_extensao(nome):
    ext = nome.lower().rsplit(".", 1)[-1] if "." in nome else ""
    m = {
        "pdf":  ft.Icons.PICTURE_AS_PDF,
        "doc":  ft.Icons.DESCRIPTION, "docx": ft.Icons.DESCRIPTION,
        "xls":  ft.Icons.TABLE_CHART, "xlsx": ft.Icons.TABLE_CHART,
        "png":  ft.Icons.IMAGE, "jpg": ft.Icons.IMAGE, "jpeg": ft.Icons.IMAGE,
        "gif":  ft.Icons.IMAGE, "webp": ft.Icons.IMAGE,
        "zip":  ft.Icons.FOLDER_ZIP, "txt": ft.Icons.TEXT_SNIPPET,
    }
    return m.get(ext, ft.Icons.ATTACH_FILE)


def _abrir_dialog(page, dialog):
    """Abre dialog usando page.open() (Flet >=0.28) com fallback para a API antiga."""
    if dialog not in page.overlay:
        page.overlay.append(dialog)
    if hasattr(page, "open"):
        try:
            page.open(dialog)
            return
        except Exception:
            pass
    dialog.open = True
    page.update()


def _fechar_dialog(page, dialog):
    if hasattr(page, "close"):
        try:
            page.close(dialog)
            return
        except Exception:
            pass
    dialog.open = False
    page.update()


# ======================================================
# SEÇÃO DE PARTES (usa get_vinculos)
# ======================================================

class _PartePicker:
    """
    Campo de busca por nome para selecionar uma parte, usando o
    ft.AutoComplete NATIVO do Flet (em vez de uma lista de sugestões
    customizada com Container + on_click, que sofria de um problema
    clássico de timing: o campo perdia o foco (on_blur) antes do
    clique no item ser processado, então a seleção não "grudava").

    Expõe `.value` (id da parte, str ou None) e `.control` (o widget
    a ser inserido na tela) — mesma interface usada antes, então o
    resto do código (salvar()) não precisa mudar.
    """

    def __init__(self, page: ft.Page, opcoes: list, valor_inicial=None, width: int = 240):
        self._page = page
        self._opcoes = opcoes or []

        # chave única "id::nome" -> permite filtrar digitando o nome
        # (o Flet filtra pela key das sugestões) e ainda recuperar o
        # id exato ao selecionar, mesmo se houver nomes repetidos.
        self._id_por_key = {}
        sugestoes = []
        for o in self._opcoes:
            key = f'{o["id"]}::{o["nome"]}'
            self._id_por_key[key] = str(o["id"])
            sugestoes.append(ft.AutoCompleteSuggestion(key=key, value=o["nome"]))

        self._nome_por_id = {str(o["id"]): o["nome"] for o in self._opcoes}

        self.value = str(valor_inicial) if valor_inicial else None
        nome_inicial = self._nome_por_id.get(self.value, "")

        self._auto = ft.AutoComplete(
            value=nome_inicial,
            suggestions=sugestoes,
            suggestions_max_height=220,
            on_select=self._on_select,
            on_change=self._on_change,
        )

        # moldura visual (o AutoComplete nativo não tem label/borda própria)
        self.control = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [ft.Icon(ft.Icons.SEARCH, size=16, color=ft.Colors.GREY_500),
                         ft.Text("Parte", size=11, color=ft.Colors.GREY_600)],
                        spacing=4,
                    ),
                    self._auto,
                ],
                spacing=2, tight=True,
            ),
            width=width,
            padding=ft.padding.symmetric(horizontal=10, vertical=6),
            border=ft.border.all(1, ft.Colors.GREY_300),
            border_radius=8,
            bgcolor=ft.Colors.WHITE,
        )

    # ------------------------------------------------------------
    def _on_select(self, e: ft.AutoCompleteSelectEvent):
        self.value = self._id_por_key.get(e.selection.key)
        self._page.update()

    def _on_change(self, e):
        # se o texto digitado não corresponde mais ao nome da parte
        # selecionada, invalida a seleção até o usuário escolher de novo
        texto_atual = e.control.value or ""
        nome_selecionado = self._nome_por_id.get(self.value)
        if nome_selecionado != texto_atual:
            self.value = None


def _build_secao_partes(page, partes_bd, vinculos_bd, cp_existentes=None):
    """
    vinculos_bd: lista de dicts da tabela 'vinculos' com campo 'tipo'.
    """
    opts_vinculos = [
        ft.dropdown.Option(v.get("tipo") or v.get("nome"))
        for v in (vinculos_bd or []) if (v.get("tipo") or v.get("nome"))
    ]

    container = ft.Column(spacing=6)
    linhas    = []
    excluir   = set()

    def criar_linha(cp_id=None, parte_id=None, tipo_vinculo=None):
        parte_picker = _PartePicker(page, partes_bd or [], valor_inicial=parte_id, width=240)

        dd_tipo = ft.Dropdown(
            options=opts_vinculos, value=tipo_vinculo,
            hint_text="Categoria de vínculo", width=180, dense=True,
        )

        def remover(e):
            container.controls.remove(row)
            if cp_id:
                excluir.add(cp_id)
            if item in linhas:
                linhas.remove(item)
            page.update()

        row = ft.Container(
            padding=ft.padding.symmetric(vertical=4, horizontal=8),
            border_radius=8, bgcolor=ft.Colors.GREY_50,
            border=ft.border.all(1, ft.Colors.GREY_200),
            content=ft.Row(
                [ft.Icon(ft.Icons.PERSON_OUTLINE, size=16, color=ft.Colors.BLUE_400),
                 parte_picker.control, dd_tipo,
                 ft.IconButton(icon=ft.Icons.REMOVE_CIRCLE_OUTLINE,
                               icon_color=ft.Colors.RED_400, icon_size=18,
                               tooltip="Remover", on_click=remover)],
                spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )
        item = {"cp_id": cp_id, "dd_parte": parte_picker, "dd_tipo": dd_tipo}
        linhas.append(item)
        container.controls.append(row)

    for cp in (cp_existentes or []):
        criar_linha(cp_id=cp.get("id"),
                    parte_id=cp.get("parte_id"),
                    tipo_vinculo=cp.get("tipo_vinculo"))

    def nova_linha(e):
        criar_linha()
        page.update()

    avisos = []
    if not partes_bd:
        avisos.append("Cadastre partes no menu 'Partes' antes de vincular.")
    if not vinculos_bd:
        avisos.append("Cadastre tipos em Tipos -> Tipos de Partes antes de vincular.")

    widget = ft.Column(
        [
            ft.Row(
                [ft.Text("Partes", weight=ft.FontWeight.BOLD, size=14),
                 ft.FilledTonalButton("Adicionar parte", icon=ft.Icons.ADD, on_click=nova_linha)],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            *[ft.Text(a, color=ft.Colors.ORANGE_700, size=12) for a in avisos],
            container,
        ],
        spacing=8,
    )
    return {"widget": widget, "linhas": linhas, "excluir": excluir}


# ======================================================
# ESCRITAS CONCORRENTES (partes, prazos, exclusões) — retry + limite
# ======================================================

# Mesma lógica do limite de uploads: muitas requisições simultâneas na
# mesma conexão podem derrubar o protocolo HTTP2 no meio
# (ConnectionTerminated / PROTOCOL_ERROR), especialmente ao vincular
# várias partes de uma vez. Limitar a concorrência reduz bastante a
# chance disso acontecer.
_LIMITE_ESCRITAS_SIMULTANEAS = asyncio.Semaphore(4)


async def _run_db_com_retry(page: ft.Page, func, *args, tentativas: int = 3, **kwargs):
    """
    Igual a run_db(), mas tenta de novo (com um pequeno intervalo) se a
    conexão cair no meio da requisição — o que passou a acontecer com
    mais frequência depois que paralelizamos várias escritas (partes,
    prazos) numa mesma chamada de salvar(). Erros "de negócio" (RLS,
    validação) falham igual na primeira tentativa e não se beneficiam
    do retry, mas repetir não causa problema — add_contrato_parte, por
    exemplo, agora usa upsert, então repetir a mesma escrita não cria
    duplicata nem quebra em erro de unicidade.
    """
    ultimo_erro = None
    async with _LIMITE_ESCRITAS_SIMULTANEAS:
        for tentativa in range(1, tentativas + 1):
            try:
                return await run_db(page, func, *args, **kwargs)
            except Exception as ex:
                ultimo_erro = ex
                if tentativa < tentativas:
                    await asyncio.sleep(0.4 * tentativa)
        raise ultimo_erro


# ======================================================
# SEÇÃO DE ANEXOS — Storage privado "Heringer"
# ======================================================

# Limita quantos anexos são enviados AO MESMO TEMPO. Em produção
# (Render -> Supabase) a banda é abundante e isso quase não importa,
# mas em conexões limitadas (ex: testes locais, internet residencial
# mais lenta), muitos uploads simultâneos disputam a mesma banda e o
# mais lento acaba pior do que se fossem enviados em pequenos lotes.
# 3 ao mesmo tempo ainda dá ganho de paralelismo sem gargalar tanto.
_LIMITE_UPLOADS_SIMULTANEOS = asyncio.Semaphore(3)


async def _upload_anexo_com_status(page: ft.Page, contrato_id, arq: dict):
    """
    Faz o upload de um anexo atualizando o texto de status da própria
    linha ("Pendente" -> "Enviando..." -> "Enviado ✓"/"Erro"), para o
    usuário acompanhar o progresso de cada arquivo individualmente
    durante o salvamento do contrato.
    """
    status = arq.get("status")

    async with _LIMITE_UPLOADS_SIMULTANEOS:
        if status:
            status.value = "Enviando..."
            status.color = ft.Colors.BLUE_600
            page.update()

        try:
            resultado = await run_db(page, upload_anexo_storage, contrato_id, arq["nome"], arq["bytes"])
            if status:
                status.value = "Enviado ✓"
                status.color = ft.Colors.GREEN_600
                page.update()
            return resultado
        except Exception:
            if status:
                status.value = "Erro no envio"
                status.color = ft.Colors.RED_600
                page.update()
            raise


def _build_secao_anexos(page, modo, anexos_existentes=None):

    pendentes = []
    excluir = []

    lista_ui = ft.Column(spacing=6)
    lbl_prog = ft.Text("", size=12, color=ft.Colors.BLUE_600)
    lbl_erro = ft.Text("", size=12, color=ft.Colors.RED_700)

    # ======================================================
    # FILE PICKER SERVICE GLOBAL
    # ======================================================

    picker_service = page.file_picker_service

    # ======================================================
    # ARQUIVO EXISTENTE
    # ======================================================

    def _row_existente(a):

        nome = a.get("nome_arquivo") or "Arquivo"
        caminho = a.get("arquivo_path") or ""

        url = ""
        if caminho:
            try:
                url = get_anexo_signed_url(caminho) or ""
            except Exception as ex:
                print("Erro signed URL:", ex)

        botoes = []

        if url:
            botoes.append(
                ft.ElevatedButton(
                    content=ft.Row(
                        [
                            ft.Icon(ft.Icons.OPEN_IN_NEW, size=14),
                            ft.Text("Abrir", size=12),
                        ],
                        spacing=4,
                        tight=True,
                    ),
                    url=url,
                )
            )

        if modo == "editar":

            def _rm(e, cam=caminho):
                lista_ui.controls.remove(row)
                if cam:
                    excluir.append(cam)
                page.update()

            botoes.append(
                ft.IconButton(
                    icon=ft.Icons.DELETE_OUTLINE,
                    icon_color=ft.Colors.RED_400,
                    on_click=_rm,
                )
            )

        row = ft.Container(
            padding=10,
            border_radius=8,
            bgcolor=ft.Colors.GREY_50,
            border=ft.border.all(1, ft.Colors.GREY_200),
            content=ft.Row(
                [
                    ft.Icon(_icone_extensao(nome), size=18),
                    ft.Text(nome, expand=True),
                    *botoes,
                ]
            ),
        )

        lista_ui.controls.append(row)

    # ======================================================
    # ARQUIVO PENDENTE
    # ======================================================

    _idx = [0]

    def _row_pendente(nome):

        cur = _idx[0]
        _idx[0] += 1

        status_txt = ft.Text("Pendente", size=11, color=ft.Colors.GREY_600)

        def _cancel(e, ci=cur):
            pendentes[:] = [p for p in pendentes if p["_idx"] != ci]
            lista_ui.controls.remove(row)
            page.update()

        row = ft.Container(
            padding=10,
            border_radius=8,
            bgcolor=ft.Colors.BLUE_50,
            border=ft.border.all(1, ft.Colors.BLUE_100),
            content=ft.Row(
                [
                    ft.Icon(_icone_extensao(nome), size=18),
                    ft.Text(nome, expand=True),
                    status_txt,
                    ft.IconButton(
                        icon=ft.Icons.CLOSE,
                        on_click=_cancel,
                    ),
                ]
            ),
        )

        lista_ui.controls.append(row)
        page.update()

        return cur, status_txt

    # ======================================================
    # EXISTENTES
    # ======================================================

    for a in (anexos_existentes or []):
        _row_existente(a)

    # ======================================================
    # FILE PICKER CALLBACK
    # ======================================================

    # Extensões aceitas (mesma checagem existe em upload_anexo_storage,
    # como segunda camada de proteção).
    EXTENSOES_PERMITIDAS = {
        ".pdf", ".doc", ".docx", ".xls", ".xlsx",
        ".jpg", ".jpeg", ".png", ".txt",
    }

    if modo != "ver":

        def on_result(e):
            if not e.files:
                return
            for f in e.files:
                try:
                    nome = f.name
                    data = bytes(f.bytes) if getattr(f, "bytes", None) else b""

                    ext = os.path.splitext(nome)[1].lower()
                    if ext not in EXTENSOES_PERMITIDAS:
                        lbl_erro.value = (
                            f"'{nome}': tipo de arquivo não permitido "
                            f"(aceitos: {', '.join(sorted(EXTENSOES_PERMITIDAS))})."
                        )
                        page.update()
                        continue

                    lbl_erro.value = ""
                    idx, status_txt = _row_pendente(nome)
                    pendentes.append({
                        "nome": nome,
                        "bytes": data,
                        "_idx": idx,
                        "_file": f,
                        "status": status_txt,
                    })
                    page.update()
                except Exception as ex:
                    lbl_erro.value = f"Erro ao processar '{getattr(f, 'name', 'arquivo')}': {ex}"
                    page.update()

        # ⭐⭐⭐ REGISTRA CALLBACK DINÂMICO ⭐⭐⭐
        picker_service.on_result_callback = on_result

        # ==================================================
        # BOTÃO
        # ==================================================

        async def abrir_picker(e):
            await picker_service.pick_files(allow_multiple=True, with_data=True)

        btn_add = ft.FilledTonalButton(
            "Adicionar arquivo",
            icon=ft.Icons.UPLOAD_FILE,
            on_click=abrir_picker,
        )

    else:
        btn_add = ft.Container()

    # ======================================================
    # WIDGET FINAL
    # ======================================================

    widget = ft.Column(
        [
            ft.Row(
                [
                    ft.Text("Anexos", weight=ft.FontWeight.BOLD),
                    btn_add,
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            lbl_prog,
            lbl_erro,
            lista_ui,
        ],
        spacing=6,
    )

    return {
        "widget": widget,
        "pendentes": pendentes,
        "excluir": excluir,
    }

# ======================================================
# NOVO CONTRATO
# ======================================================

async def novo_contrato_dialog(page: ft.Page, atualizar_lista):

    tenant_id = _get_tenant(page)
    if not tenant_id:
        _snack(page, "Tenant não identificado. Faça login novamente.")
        return

    # FIX PERFORMANCE: essas 4 consultas são independentes entre si —
    # antes rodavam uma de cada vez (4 idas e vindas de rede em série).
    # Agora rodam ao mesmo tempo com asyncio.gather.
    clientes, partes_bd, vinculos_bd, tipos_contrato = await asyncio.gather(
        run_db(page, get_clientes, tenant_id),
        run_db(page, get_partes, tenant_id),
        run_db(page, get_vinculos, tenant_id),
        run_db(page, get_tipos_contratos, tenant_id),
    )
    clientes       = clientes or []
    partes_bd      = partes_bd or []
    vinculos_bd    = vinculos_bd or []
    tipos_contrato = tipos_contrato or []

    if not clientes:
        _snack(page, "Nenhum cliente cadastrado.")
        return

    # ======================================================
    # CLIENTE + TIPO CONTRATO (LADO A LADO)
    # ======================================================

    dd_cliente = ft.Dropdown(
        label="Cliente",
        width=260,
        options=[ft.dropdown.Option(str(c["id"]), c["nome"]) for c in clientes],
    )

    dd_tipo_contrato = ft.Dropdown(
        label="Categoria de contrato",
        width=260,
        options=[
            ft.dropdown.Option(t["nome"], t["nome"])
            for t in tipos_contrato
        ],
    )

    # ======================================================
    # RESPONSÁVEL
    # ======================================================

    tf_resp = ft.TextField(
        label="Responsável",
        value=_get_usuario_nome(page),
        disabled=True,
        width=380
    )

    # ======================================================
    # ÍNDICE (NOVO CAMPO)
    # ======================================================

    tf_indice = ft.TextField(
        label="Identificador",
        width=380,
        hint_text="Identificador do contrato"
    )

    # ======================================================
    # CLÁUSULAS
    # ======================================================

    tf_clausulas = ft.TextField(
        label="Observação / Cláusulas",
        width=380,
        multiline=True,
        min_lines=3,
        max_lines=5,
    )

    # ======================================================
    # DATAS
    # ======================================================

    tf_data_ini = ft.TextField(
        label="Data inicial (DD/MM/AAAA)",
        width=190,
        hint_text="Ex: 01/01/2025",
        read_only=True
    )

    tf_data_ass = ft.TextField(
        label="Data de assinatura",
        width=190,
        hint_text="Ex: 01/01/2025",
        read_only=True
    )

    tf_vig = ft.TextField(
        label="Vigência (meses)",
        width=140,
        keyboard_type=ft.KeyboardType.NUMBER
    )

    tf_fim = ft.TextField(
        label="Termo final",
        read_only=True,
        width=190
    )

    # ======================================================
    # RECALCULAR VIGÊNCIA
    # ======================================================

    def recalcular():
        dt = _parse_db(data_br_para_db(tf_data_ini.value or ""))
        if dt and _is_int_str(tf_vig.value):
            tf_fim.value = data_db_para_br(
                _format_db(_data_por_meses(dt, int(tf_vig.value)))
            )
        else:
            tf_fim.value = ""

    def _set_data_ini(d):
        tf_data_ini.value = d.strftime("%d/%m/%Y")
        recalcular()
        page.update()

    def _set_data_ass(d):
        tf_data_ass.value = d.strftime("%d/%m/%Y")
        page.update()

    def cal_ini(e):
        calendario_ptbr(page, on_select=_set_data_ini)

    def cal_ass(e):
        calendario_ptbr(page, on_select=_set_data_ass)

    tf_vig.on_change = lambda e: (recalcular(), page.update())

    # ======================================================
    # PARTES
    # ======================================================

    secao_partes = _build_secao_partes(page, partes_bd, vinculos_bd)

    # ======================================================
    # ANEXOS
    # ======================================================

    secao_anexos = _build_secao_anexos(page, modo="editar")

    # ======================================================
    # SALVAR
    # ======================================================

    loading_salvar = ft.ProgressRing(width=16, height=16, stroke_width=2, visible=False)

    async def salvar(e):

        if not dd_cliente.value or not tf_data_ini.value:
            _snack(page, "Cliente e data inicial são obrigatórios.")
            return

        if not data_br_para_db(tf_data_ini.value):
            _snack(page, "Data inválida.")
            return

        if tf_vig.value and not _is_int_str(tf_vig.value):
            _snack(page, "Vigência inválida.")
            return

        # feedback visual imediato + evita duplo clique/duplo contrato
        btn_salvar.disabled = True
        loading_salvar.visible = True
        page.update()

        try:
            cli  = next(c for c in clientes if str(c["id"]) == dd_cliente.value)
            contratos_do_cliente = await run_db(page, get_contratos_por_cliente, cli["id"], tenant_id)
            nome = _gerar_nome(cli["sigla"], contratos_do_cliente)

            try:
                novo = await run_db(page, add_contrato, {
                    "tenant_id":       tenant_id,
                    "nome":            nome,
                    "cliente_id":      cli["id"],
                    "responsavel":     tf_resp.value or "",
                    "indice":          tf_indice.value or None,
                    "tipo_contrato":   dd_tipo_contrato.value or None,
                    "clausulas":       tf_clausulas.value or "",
                    "data_inicial":    data_br_para_db(tf_data_ini.value),
                    "data_assinatura": data_br_para_db(tf_data_ass.value)
                                        if tf_data_ass.value else None,
                    "vigencia":        int(tf_vig.value)
                                        if _is_int_str(tf_vig.value) else None,
                    "termo_final":     data_br_para_db(tf_fim.value),
                })

            except Exception as ex:
                _snack(page, f"Erro ao criar contrato: {ex}")
                return

            if novo:
                # FIX PERFORMANCE: antes, cada parte vinculada e cada anexo
                # era gravado um de cada vez, esperando a resposta do
                # Supabase a cada chamada (N + M viagens de rede em série).
                # Agora todas rodam em paralelo com asyncio.gather — o
                # tempo total passa a ser o da chamada mais lenta, não a
                # soma de todas.
                tarefas = []

                for ln in secao_partes["linhas"]:
                    if ln["dd_parte"].value and ln["dd_tipo"].value:
                        tarefas.append(_run_db_com_retry(
                            page, add_contrato_parte,
                            novo["id"],
                            int(ln["dd_parte"].value),
                            ln["dd_tipo"].value,
                            tenant_id,
                        ))

                for arq in secao_anexos["pendentes"]:
                    tarefas.append(_upload_anexo_com_status(page, novo["id"], arq))

                if tarefas:
                    resultados = await asyncio.gather(*tarefas, return_exceptions=True)
                    erros = [r for r in resultados if isinstance(r, Exception)]
                    if erros:
                        _snack(page, f"Contrato criado, mas {len(erros)} item(ns) falharam ao salvar.")

            _fechar_dialog(page, dialog)
            atualizar_lista()
            _snack(page, f"Contrato {nome} criado.")

        finally:
            btn_salvar.disabled = False
            loading_salvar.visible = False
            page.update()

    btn_salvar = ft.FilledButton("Salvar", on_click=salvar)

    # ======================================================
    # DIALOG
    # ======================================================

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Novo Contrato"),
        content=ft.Container(
            height=580,
            content=ft.Column(
                [
                    ft.Row([dd_cliente, dd_tipo_contrato], spacing=12),

                    secao_partes["widget"],
                    ft.Divider(height=1),

                    tf_resp,

                    # ✅ ÍNDICE antes das cláusulas
                    tf_indice,
                    tf_clausulas,

                    ft.Row(
                        spacing=20,
                        wrap=True,
                        controls=[
                            ft.Column(
                                spacing=6,
                                controls=[
                                    ft.OutlinedButton(
                                        "Data inicial",
                                        icon=ft.Icons.CALENDAR_TODAY,
                                        on_click=cal_ini
                                    ),
                                    tf_data_ini,
                                ],
                            ),
                            ft.Column(
                                spacing=6,
                                controls=[
                                    ft.OutlinedButton(
                                        "Data assinatura",
                                        icon=ft.Icons.CALENDAR_TODAY,
                                        on_click=cal_ass
                                    ),
                                    tf_data_ass,
            ],
        ),
    ],
),
                    ft.Row([tf_vig, tf_fim], spacing=16),

                    ft.Divider(height=1),
                    secao_anexos["widget"],
                ],
                spacing=10,
                scroll=ft.ScrollMode.AUTO,
            ),
        ),
        actions=[
            ft.TextButton("Cancelar",
                          on_click=lambda e: _fechar_dialog(page, dialog)),
            loading_salvar,
            btn_salvar,
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    _abrir_dialog(page, dialog)
# ======================================================
# EDITAR CONTRATO
# ======================================================

async def editar_contrato_dialog(page: ft.Page, contrato: dict, on_save):

    data_base = _parse_db(contrato.get("data_inicial"))
    if not data_base:
        _snack(page, "Data inicial inválida.")
        return

    tenant_id = _get_tenant(page)
    if not tenant_id:
        _snack(page, "Tenant não identificado. Faça login novamente.")
        return

    # FIX PERFORMANCE: 6 consultas independentes, antes feitas uma de
    # cada vez (6 idas e vindas de rede em série) espalhadas pelo meio
    # da montagem da tela. Agora todas rodam juntas, no início, com
    # asyncio.gather — o restante da função só monta a UI com os
    # dados que já chegaram.
    (
        partes_bd, vinculos_bd, tipos_contrato,
        cp_existentes, prazos, anexos_existentes, tipos_prazos,
    ) = await asyncio.gather(
        run_db(page, get_partes, tenant_id),
        run_db(page, get_vinculos, tenant_id),
        run_db(page, get_tipos_contratos, tenant_id),
        run_db(page, get_contrato_partes, contrato["id"]),
        run_db(page, get_prazos_por_contrato, contrato["id"]),
        run_db(page, list_anexos_storage, contrato["id"]),
        run_db(page, get_tipos_prazos, tenant_id),
    )
    partes_bd         = partes_bd or []
    vinculos_bd       = vinculos_bd or []
    tipos_contrato    = tipos_contrato or []
    cp_existentes     = cp_existentes or []
    prazos            = prazos or []
    anexos_existentes = anexos_existentes or []
    tipos_prazos      = tipos_prazos or []

    # ── Mesmos campos do Novo, com valores pré-preenchidos ──

    # Cliente: read-only (não muda no editar)
    dd_cliente = ft.Dropdown(
        label="Cliente",
        width=260,
        options=[ft.dropdown.Option(
            str((contrato.get("clientes") or {}).get("id") or contrato.get("cliente_id") or ""),
            (contrato.get("clientes") or {}).get("nome", ""),
        )],
        value=str((contrato.get("clientes") or {}).get("id") or contrato.get("cliente_id") or ""),
        disabled=True,
    )

    dd_tipo_contrato = ft.Dropdown(
        label="Categoria de contrato",
        width=260,
        value=contrato.get("tipo_contrato"),
        options=[ft.dropdown.Option(t["nome"], t["nome"]) for t in tipos_contrato],
    )

    tf_resp = ft.TextField(
        label="Responsável",
        value=contrato.get("responsavel") or _get_usuario_nome(page),
        disabled=True,
        width=380,
    )

    tf_indice = ft.TextField(
        label="Identificador",
        value=contrato.get("indice") or "",
        width=380,
        hint_text="Ex: IPCA, IGPM, INPC...",
    )

    tf_clausulas = ft.TextField(
        label="Observação / Cláusulas",
        value=contrato.get("clausulas") or "",
        width=380,
        multiline=True,
        min_lines=3,
        max_lines=5,
    )

    tf_data_ini = ft.TextField(
        label="Data inicial (DD/MM/AAAA)",
        value=data_db_para_br(contrato.get("data_inicial")),
        width=190,
        read_only=True,
        disabled=True,
    )

    tf_data_ass = ft.TextField(
        label="Data de assinatura",
        value=data_db_para_br(contrato.get("data_assinatura")),
        width=190,
        read_only=True,
    )

    tf_vig = ft.TextField(
        label="Vigência (meses)",
        value=str(contrato.get("vigencia") or ""),
        width=140,
        keyboard_type=ft.KeyboardType.NUMBER,
    )

    tf_fim = ft.TextField(
        label="Termo final",
        value=data_db_para_br(contrato.get("termo_final")),
        width=190,
        read_only=True,
    )

    def recalcular():
        if _is_int_str(tf_vig.value):
            tf_fim.value = data_db_para_br(
                _format_db(_data_por_meses(data_base, int(tf_vig.value)))
            )
        else:
            tf_fim.value = ""
        page.update()

    def _set_data_ass(d):
        tf_data_ass.value = d.strftime("%d/%m/%Y")
        page.update()

    def cal_ass(e):
        calendario_ptbr(page, on_select=_set_data_ass)

    tf_vig.on_change = lambda e: recalcular()
    recalcular()

    # ── Partes ──
    secao_partes  = _build_secao_partes(page, partes_bd, vinculos_bd, cp_existentes)

    # ── Prazos ──
    container_prazos = ft.Column(spacing=6)
    linhas_prazos    = []
    excluir_prazos   = set()

    def criar_linha_prazo(pid, data_inicio="", meses="", obs="", tipo=None, existente=False):
        tf_i = ft.TextField(label="Data Início", value=data_db_para_br(data_inicio),
                            width=140, read_only=True)
        tf_m = ft.TextField(
            label="Meses", value=str(meses) if meses not in (None, "", 0) else "",
            width=80,
            input_filter=ft.NumbersOnlyInputFilter(),
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        # Calculada automaticamente (Data Início + Meses) — não editável.
        tf_d = ft.TextField(label="Data", width=140, read_only=True)
        dd_t = ft.Dropdown(
            label="Tipo", value=tipo, width=220, menu_width=280,
            options=[ft.dropdown.Option(t["nome"]) for t in tipos_prazos],
        )
        tf_o = ft.TextField(label="Observação", value=obs or "", width=200)

        def _recalcular(e=None):
            if len(tf_m.value or "") > 3:
                tf_m.value = tf_m.value[:3]
            iso_inicio = data_br_para_db(tf_i.value)
            nova = somar_meses(iso_inicio, tf_m.value)
            tf_d.value = data_db_para_br(nova) if nova else ""
            page.update()

        tf_m.on_change = _recalcular

        def _set_data_inicio(d):
            tf_i.value = d.strftime("%d/%m/%Y")
            _recalcular()

        def cal_p(e):
            calendario_ptbr(page, on_select=_set_data_inicio)

        # Calcula a data já na criação da linha (prazos existentes)
        _recalcular()

        def remover(e):
            container_prazos.controls.remove(row)
            if existente and pid:
                excluir_prazos.add(pid)
            page.update()

        row = ft.Row(
            [ft.OutlinedButton("Data Início", icon=ft.Icons.CALENDAR_TODAY,
                               height=32, on_click=cal_p),
             tf_i,
             tf_m,
             tf_d,
             dd_t,
             tf_o,
             ft.IconButton(icon=ft.Icons.CLOSE, icon_size=18, on_click=remover)],
            spacing=6, wrap=True,
        )
        linhas_prazos.append((pid, tf_i, tf_m, tf_d, dd_t, tf_o))
        container_prazos.controls.append(row)

    for p in prazos:
        criar_linha_prazo(p["id"],
                          p.get("data_criacao"),
                          p.get("meses"),
                          p.get("observacao"),
                          p.get("tipo"), True)

    def novo_prazo(e):
        criar_linha_prazo(None)
        page.update()

    # ── Anexos ──
    secao_anexos = _build_secao_anexos(page, modo="editar",
                                       anexos_existentes=anexos_existentes)

    loading_salvar = ft.ProgressRing(width=16, height=16, stroke_width=2, visible=False)

    # ── Salvar ──
    async def salvar(e):
        if tf_vig.value and not _is_int_str(tf_vig.value):
            _snack(page, "Vigência inválida.")
            return

        btn_salvar.disabled = True
        loading_salvar.visible = True
        page.update()

        try:
            await run_db(page, update_contrato, contrato["id"], {
                "tipo_contrato":   dd_tipo_contrato.value or None,
                "responsavel":     tf_resp.value or "",
                "indice":          tf_indice.value or None,
                "clausulas":       tf_clausulas.value or "",
                "data_assinatura": data_br_para_db(tf_data_ass.value) if tf_data_ass.value else None,
                "vigencia":        int(tf_vig.value) if _is_int_str(tf_vig.value) else None,
                "termo_final":     data_br_para_db(tf_fim.value),
            })

            # FIX PERFORMANCE: prazos, partes e anexos eram gravados um de
            # cada vez, em série (cada `await` esperando a rede antes do
            # próximo). Agora todas essas operações independentes rodam em
            # paralelo com asyncio.gather — o tempo total passa a ser o da
            # operação mais lenta, não a soma de todas.
            tarefas = []

            for pid in excluir_prazos:
                tarefas.append(_run_db_com_retry(page, update_prazo, pid, {"ativo": False}))

            for pid, tf_i, tf_m, tf_d, dd_t, tf_o in linhas_prazos:
                if pid in excluir_prazos:
                    continue
                if not tf_i.value and not tf_d.value and not tf_o.value and not dd_t.value:
                    continue
                payload = {
                    "data_criacao":    data_br_para_db(tf_i.value),
                    "meses":           int(tf_m.value) if _is_int_str(tf_m.value) else 0,
                    "data_vencimento": data_br_para_db(tf_d.value),
                    "observacao":      tf_o.value or "",
                    "tipo":            dd_t.value,
                }
                if pid:
                    tarefas.append(_run_db_com_retry(page, update_prazo, pid, payload))
                else:
                    tarefas.append(_run_db_com_retry(
                        page, add_prazo,
                        contrato_id=contrato["id"],
                        meses=payload["meses"],
                        observacao=tf_o.value,
                        data_criacao=payload["data_criacao"],
                        data_vencimento=payload["data_vencimento"],
                        tenant_id=tenant_id,
                        tipo=dd_t.value,
                    ))

            for cp_id in secao_partes["excluir"]:
                tarefas.append(_run_db_com_retry(page, delete_contrato_parte, cp_id))
            for ln in secao_partes["linhas"]:
                cp_id = ln["cp_id"]
                p_val = ln["dd_parte"].value
                t_val = ln["dd_tipo"].value
                if cp_id in secao_partes["excluir"] or not p_val or not t_val:
                    continue
                if cp_id is None:
                    tarefas.append(_run_db_com_retry(page, add_contrato_parte, contrato["id"], int(p_val), t_val, tenant_id))

            for caminho in secao_anexos["excluir"]:
                tarefas.append(_run_db_com_retry(page, delete_anexo_storage, caminho))
            for arq in secao_anexos["pendentes"]:
                tarefas.append(_upload_anexo_com_status(page, contrato["id"], arq))

            if tarefas:
                resultados = await asyncio.gather(*tarefas, return_exceptions=True)
                erros = [r for r in resultados if isinstance(r, Exception)]
                if erros:
                    _snack(page, f"Contrato salvo, mas {len(erros)} item(ns) falharam.")

        except Exception as ex:
            _snack(page, f"Erro: {ex}")
            return
        finally:
            btn_salvar.disabled = False
            loading_salvar.visible = False
            page.update()

        _fechar_dialog(page, dialog)
        on_save()
        _snack(page, "Contrato atualizado.")

    btn_salvar = ft.FilledButton("Salvar", on_click=salvar)

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text(f"Editar — {contrato.get('nome', '')}"),
        content=ft.Container(
            height=660,
            content=ft.Column(
                [
                    ft.Row([dd_cliente, dd_tipo_contrato], spacing=12),

                    secao_partes["widget"],
                    ft.Divider(height=1),

                    tf_resp,
                    tf_indice,
                    tf_clausulas,

                    ft.Row(
                        spacing=20,
                        wrap=True,
                        controls=[
                            ft.Column(spacing=6, controls=[
                                ft.Text("Data inicial:", size=12, color=ft.Colors.GREY_600),
                                tf_data_ini,
                            ]),
                            ft.Column(spacing=6, controls=[
                                ft.OutlinedButton(
                                    "Data assinatura",
                                    icon=ft.Icons.CALENDAR_TODAY,
                                    on_click=cal_ass,
                                ),
                                tf_data_ass,
                            ]),
                        ],
                    ),

                    ft.Row([tf_vig, tf_fim], spacing=16),

                    ft.Divider(height=1),

                    ft.Row(
                        [ft.Text("Prazos", weight=ft.FontWeight.BOLD),
                         ft.FilledButton("Adicionar prazo", height=32, on_click=novo_prazo)],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    container_prazos,

                    ft.Divider(height=1),
                    secao_anexos["widget"],
                ],
                spacing=10,
                scroll=ft.ScrollMode.AUTO,
            ),
        ),
        actions=[
            ft.TextButton("Cancelar", on_click=lambda e: _fechar_dialog(page, dialog)),
            loading_salvar,
            btn_salvar,
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    _abrir_dialog(page, dialog)


# ======================================================
# VER CONTRATO (somente leitura)
# ======================================================

async def ver_contrato_dialog(page: ft.Page, contrato: dict, clientes_map: dict):

    tenant_id = _get_tenant(page)

    # FIX PERFORMANCE: eram 7 consultas — 5 em série no topo, e mais 2
    # repetidas lá embaixo (get_partes/get_vinculos de novo, buscando
    # a MESMA coisa que "todas_partes" já tinha trazido). Agora são 6
    # consultas únicas, todas paralelas, num só lugar.
    (
        prazos, cp_lista, todas_partes, anexos, tipos_contrato, vinculos_bd,
    ) = await asyncio.gather(
        run_db(page, get_prazos_por_contrato, contrato["id"]),
        run_db(page, get_contrato_partes, contrato["id"]),
        run_db(page, get_partes, tenant_id),
        run_db(page, list_anexos_storage, contrato["id"]),
        run_db(page, get_tipos_contratos, tenant_id),
        run_db(page, get_vinculos, tenant_id),
    )
    prazos         = prazos or []
    cp_lista       = cp_lista or []
    todas_partes   = todas_partes or []
    anexos         = anexos or []
    tipos_contrato = tipos_contrato or []
    vinculos_bd    = vinculos_bd or []
    partes_map   = {str(p["id"]): p for p in todas_partes}

    nome_cliente = clientes_map.get(contrato.get("cliente_id"), "-")

    # ── Mesmos campos do Novo, todos disabled/read_only ──

    dd_cliente = ft.Dropdown(
        label="Cliente",
        width=260,
        options=[ft.dropdown.Option("_", nome_cliente)],
        value="_",
        disabled=True,
    )

    dd_tipo_contrato = ft.Dropdown(
        label="Categoria de contrato",
        width=260,
        value=contrato.get("tipo_contrato"),
        options=[ft.dropdown.Option(t["nome"], t["nome"]) for t in tipos_contrato],
        disabled=True,
    )

    tf_resp = ft.TextField(
        label="Responsável",
        value=contrato.get("responsavel") or "-",
        disabled=True,
        width=380,
    )

    tf_indice = ft.TextField(
        label="Indicador",
        value=contrato.get("indice") or "-",
        width=380,
        read_only=True,
    )

    tf_clausulas = ft.TextField(
        label="Observação / Cláusulas",
        value=contrato.get("clausulas") or "",
        width=380,
        multiline=True,
        min_lines=3,
        max_lines=5,
        read_only=True,
    )

    tf_data_ini = ft.TextField(
        label="Data inicial (DD/MM/AAAA)",
        value=data_db_para_br(contrato.get("data_inicial")),
        width=190,
        read_only=True,
    )

    tf_data_ass = ft.TextField(
        label="Data de assinatura",
        value=data_db_para_br(contrato.get("data_assinatura")),
        width=190,
        read_only=True,
    )

    tf_vig = ft.TextField(
        label="Vigência (meses)",
        value=str(contrato.get("vigencia") or ""),
        width=140,
        read_only=True,
    )

    tf_fim = ft.TextField(
        label="Termo final",
        value=data_db_para_br(contrato.get("termo_final")),
        width=190,
        read_only=True,
    )

    # ── Partes (read-only dropdowns) ──
    partes_bd     = todas_partes
    opts_partes   = [ft.dropdown.Option(str(p["id"]), p["nome"]) for p in partes_bd]
    opts_vinculos = [
        ft.dropdown.Option(v.get("tipo") or v.get("nome"))
        for v in vinculos_bd if (v.get("tipo") or v.get("nome"))
    ]

    partes_col = ft.Column(spacing=6)
    for cp in cp_lista:
        partes_col.controls.append(
            ft.Container(
                padding=ft.padding.symmetric(vertical=4, horizontal=8),
                border_radius=8, bgcolor=ft.Colors.GREY_50,
                border=ft.border.all(1, ft.Colors.GREY_200),
                content=ft.Row([
                    ft.Icon(ft.Icons.PERSON_OUTLINE, size=16, color=ft.Colors.BLUE_400),
                    ft.Dropdown(options=opts_partes, value=str(cp.get("parte_id") or ""),
                                width=240, dense=True, disabled=True),
                    ft.Dropdown(options=opts_vinculos, value=cp.get("tipo_vinculo"),
                                width=180, dense=True, disabled=True),
                ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            )
        )
    if not cp_lista:
        partes_col.controls.append(
            ft.Text("Nenhuma parte vinculada.", color=ft.Colors.GREY_500, italic=True, size=13)
        )

    # ── Prazos (read-only) ──
    prazos_col = ft.Column(spacing=6)
    for p in prazos:
        prazos_col.controls.append(
            ft.Container(
                padding=ft.padding.symmetric(vertical=4, horizontal=8),
                border_radius=8, bgcolor=ft.Colors.GREY_50,
                border=ft.border.all(1, ft.Colors.GREY_200),
                content=ft.Row([
                    ft.Icon(ft.Icons.CALENDAR_TODAY, size=14, color=ft.Colors.BLUE_400),
                    ft.Text(f"Início: {data_db_para_br(p.get('data_criacao')) or '-'}",
                            size=12, color=ft.Colors.GREY_600),
                    ft.Text(f"{p.get('meses') or 0} meses",
                            size=12, color=ft.Colors.GREY_600),
                    ft.Text("=", size=12, color=ft.Colors.GREY_400),
                    ft.Text(data_db_para_br(p.get("data_vencimento")),
                            weight=ft.FontWeight.W_500, size=13),
                    ft.Container(
                        padding=ft.padding.symmetric(horizontal=8, vertical=2),
                        border_radius=6, bgcolor=ft.Colors.BLUE_50,
                        content=ft.Text(p.get("tipo") or "-", size=12,
                                        color=ft.Colors.BLUE_700,
                                        weight=ft.FontWeight.W_600),
                    ) if p.get("tipo") else ft.Container(),
                    ft.Text(f"— {p.get('observacao') or ''}",
                            color=ft.Colors.GREY_600, size=13),
                ], spacing=6, wrap=True),
            )
        )
    if not prazos:
        prazos_col.controls.append(
            ft.Text("Nenhum prazo cadastrado.", color=ft.Colors.GREY_500, italic=True, size=13)
        )

    # ── Anexos (modo ver) ──
    secao_anexos = _build_secao_anexos(page, modo="ver", anexos_existentes=anexos)

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text(contrato.get("nome", ""), weight=ft.FontWeight.BOLD),
        content=ft.Container(
            height=660,
            content=ft.Column(
                [
                    ft.Row([dd_cliente, dd_tipo_contrato], spacing=12),

                    ft.Column([
                        ft.Row([ft.Text("Partes", weight=ft.FontWeight.BOLD, size=14)]),
                        partes_col,
                    ], spacing=8),

                    ft.Divider(height=1),

                    tf_resp,
                    tf_indice,
                    tf_clausulas,

                    ft.Row(
                        spacing=20,
                        wrap=True,
                        controls=[
                            ft.Column(spacing=6, controls=[
                                ft.Text("Data inicial:", size=12, color=ft.Colors.GREY_600),
                                tf_data_ini,
                            ]),
                            ft.Column(spacing=6, controls=[
                                ft.Text("Data assinatura:", size=12, color=ft.Colors.GREY_600),
                                tf_data_ass,
                            ]),
                        ],
                    ),

                    ft.Row([tf_vig, tf_fim], spacing=16),

                    ft.Divider(height=1),

                    ft.Column([
                        ft.Text("Prazos", weight=ft.FontWeight.BOLD, size=14),
                        prazos_col,
                    ], spacing=8),

                    ft.Divider(height=1),
                    secao_anexos["widget"],
                ],
                spacing=10,
                scroll=ft.ScrollMode.AUTO,
            ),
        ),
        actions=[
            ft.TextButton("Fechar", on_click=lambda e: _fechar_dialog(page, dialog)),
        ],
    )

    _abrir_dialog(page, dialog)