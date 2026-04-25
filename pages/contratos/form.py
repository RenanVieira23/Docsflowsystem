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
import os
import time
from datetime import datetime
from dateutil.relativedelta import relativedelta


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
)

from utils.calendario_ptbr import calendario_ptbr
from utils.dataptbr import data_br_para_db, data_db_para_br


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

def _build_secao_partes(page, partes_bd, vinculos_bd, cp_existentes=None):
    """
    vinculos_bd: lista de dicts da tabela 'vinculos' com campo 'tipo'.
    """
    opts_partes   = [ft.dropdown.Option(str(p["id"]), p["nome"]) for p in (partes_bd or [])]
    opts_vinculos = [
        ft.dropdown.Option(v.get("tipo") or v.get("nome"))
        for v in (vinculos_bd or []) if (v.get("tipo") or v.get("nome"))
    ]

    container = ft.Column(spacing=6)
    linhas    = []
    excluir   = set()

    def criar_linha(cp_id=None, parte_id=None, tipo_vinculo=None):
        dd_parte = ft.Dropdown(
            options=opts_partes, value=str(parte_id) if parte_id else None,
            hint_text="Selecionar parte", width=240, dense=True,
        )
        dd_tipo = ft.Dropdown(
            options=opts_vinculos, value=tipo_vinculo,
            hint_text="Tipo de vínculo", width=180, dense=True,
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
                 dd_parte, dd_tipo,
                 ft.IconButton(icon=ft.Icons.REMOVE_CIRCLE_OUTLINE,
                               icon_color=ft.Colors.RED_400, icon_size=18,
                               tooltip="Remover", on_click=remover)],
                spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )
        item = {"cp_id": cp_id, "dd_parte": dd_parte, "dd_tipo": dd_tipo}
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
# SEÇÃO DE ANEXOS — Storage privado "Heringer"
# ======================================================

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
                    ft.Text("Pendente", size=11),
                    ft.IconButton(
                        icon=ft.Icons.CLOSE,
                        on_click=_cancel,
                    ),
                ]
            ),
        )

        lista_ui.controls.append(row)
        page.update()

        return cur

    # ======================================================
    # EXISTENTES
    # ======================================================

    for a in (anexos_existentes or []):
        _row_existente(a)

    # ======================================================
    # FILE PICKER CALLBACK
    # ======================================================

    if modo != "ver":

        def on_result(e):
            lbl_erro.value = "on_result fired!"
            page.update()
            if not e.files:
                return
            for f in e.files:
                try:
                    nome = f.name
                    size = getattr(f, 'size', 0)
                    lbl_erro.value = f"File: {nome} size={size} - waiting for save"
                    page.update()
                    idx = _row_pendente(nome)
                    pendentes.append({
                        "nome": nome,
                        "bytes": b"",
                        "_idx": idx,
                        "_file": f,
                    })
                except Exception as ex:
                    lbl_erro.value = str(ex)
                    page.update()

        # ⭐⭐⭐ REGISTRA CALLBACK DINÂMICO ⭐⭐⭐
        picker_service.on_result_callback = on_result

        # ==================================================
        # BOTÃO
        # ==================================================

        def abrir_picker(e):
            page.run_task(picker_service.pick_files, allow_multiple=True)

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

def novo_contrato_dialog(page: ft.Page, atualizar_lista):

    tenant_id = _get_tenant(page)
    if not tenant_id:
        _snack(page, "Tenant não identificado. Faça login novamente.")
        return

    clientes    = get_clientes(tenant_id) or []
    partes_bd   = get_partes() or []
    vinculos_bd = get_vinculos(tenant_id) or []

    if not clientes:
        _snack(page, "Nenhum cliente cadastrado.")
        return

    dd_cliente = ft.Dropdown(
        label="Cliente", width=380,
        options=[ft.dropdown.Option(str(c["id"]), c["nome"]) for c in clientes],
    )

    # Responsável read-only (usuário logado)
    tf_resp = ft.TextField(label="Responsável",
                           value=_get_usuario_nome(page),
                           disabled=True, width=380)

    tf_clausulas = ft.TextField(
        label="Observação / Cláusulas", width=380,
        multiline=True, min_lines=3, max_lines=5,
    )

    tf_data_ini = ft.TextField(label="Data inicial (DD/MM/AAAA)",
                               width=190, hint_text="Ex: 01/01/2025", read_only=True)
    tf_data_ass = ft.TextField(label="Data de assinatura",
                               width=190, hint_text="Ex: 01/01/2025", read_only=True)
    tf_vig      = ft.TextField(label="Vigência (meses)", width=140,
                               keyboard_type=ft.KeyboardType.NUMBER)
    tf_fim      = ft.TextField(label="Termo final", read_only=True, width=190)

    def recalcular():
        dt = _parse_db(data_br_para_db(tf_data_ini.value or ""))
        if dt and _is_int_str(tf_vig.value):
            tf_fim.value = data_db_para_br(_format_db(_data_por_meses(dt, int(tf_vig.value))))
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

    # PARTES
    secao_partes = _build_secao_partes(page, partes_bd, vinculos_bd)

    # ANEXOS (NOVO = modo edição)
    secao_anexos = _build_secao_anexos(page, modo="editar")

    def salvar(e):
        print(f"🔥 SALVAR called: cliente={dd_cliente.value}, data={tf_data_ini.value}")
        if not dd_cliente.value or not tf_data_ini.value:
            _snack(page, "Cliente e data inicial são obrigatórios.")
            return
        if not data_br_para_db(tf_data_ini.value):
            _snack(page, "Data inválida. Use DD/MM/AAAA.")
            return
        if tf_vig.value and not _is_int_str(tf_vig.value):
            _snack(page, "Vigência inválida.")
            return

        cli  = next(c for c in clientes if str(c["id"]) == dd_cliente.value)
        nome = _gerar_nome(cli["sigla"], get_contratos_por_cliente(cli["id"], tenant_id))

        try:
            novo = add_contrato({
                "tenant_id":       tenant_id,
                "nome":            nome,
                "cliente_id":      cli["id"],
                "responsavel":     tf_resp.value or "",
                "clausulas":       tf_clausulas.value or "",
                "data_inicial":    data_br_para_db(tf_data_ini.value),
                "data_assinatura": data_br_para_db(tf_data_ass.value) if tf_data_ass.value else None,
                "vigencia":        int(tf_vig.value) if _is_int_str(tf_vig.value) else None,
                "termo_final":     data_br_para_db(tf_fim.value),
            })
        except Exception as ex:
            print(f"❌ add_contrato error: {ex}")
            _snack(page, f"Erro ao criar contrato: {ex}")
            return

        if novo:
            for ln in secao_partes["linhas"]:
                if ln["dd_parte"].value and ln["dd_tipo"].value:
                    add_contrato_parte(novo["id"],
                                       int(ln["dd_parte"].value),
                                       ln["dd_tipo"].value)

            # CORREÇÃO: Storage-only — sem tabela 'anexos'.
            # Removido bloco duplicado e chamadas a add_anexo (não importado
            # e inconsistente com a abordagem de editar_contrato_dialog).
            picker_service = page.file_picker_service
            for arq in secao_anexos["pendentes"]:
                f = arq.get("_file")
                if f is None:
                    continue
                upload_list = [ft.FilePickerUploadFile(
                    name=f.name,
                    upload_url=page.get_upload_url(f.name, 60),
                )]
                picker_service.upload(upload_list)
                time.sleep(2)
                local_path = os.path.join(UPLOAD_DIR, f.name)
                try:
                    if os.path.exists(local_path):
                        with open(local_path, "rb") as fh:
                            data = fh.read()
                        upload_anexo_storage(novo["id"], f.name, data)
                        _snack(page, f"Arquivo {f.name} enviado!")
                    else:
                        _snack(page, f"Arquivo {f.name} não encontrado no servidor")
                except Exception as ex:
                    _snack(page, f"Erro: {ex}")

        _fechar_dialog(page, dialog)
        atualizar_lista()
        _snack(page, f"Contrato {nome} criado.")

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Novo Contrato"),
        content=ft.Container(
            height=580,
            content=ft.Column(
                [
                    dd_cliente,
                    secao_partes["widget"],
                    ft.Divider(height=1),
                    tf_resp,
                    tf_clausulas,
                    ft.Row([
                        ft.OutlinedButton("Data inicial",     icon=ft.Icons.CALENDAR_TODAY,
                                          height=36, on_click=cal_ini),
                        tf_data_ini,
                        ft.OutlinedButton("Data assinatura",  icon=ft.Icons.CALENDAR_TODAY,
                                          height=36, on_click=cal_ass),
                        tf_data_ass,
                    ], spacing=8, wrap=True),
                    ft.Row([tf_vig, tf_fim], spacing=16),
                    ft.Divider(height=1),
                    secao_anexos["widget"],
                ],
                spacing=10, scroll=ft.ScrollMode.AUTO,
            ),
        ),
        actions=[
            ft.TextButton("Cancelar", on_click=lambda e: _fechar_dialog(page, dialog)),
            ft.FilledButton("Salvar", on_click=salvar),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    _abrir_dialog(page, dialog)


# ======================================================
# EDITAR CONTRATO
# ======================================================

def editar_contrato_dialog(page: ft.Page, contrato: dict, on_save):

    data_base = _parse_db(contrato.get("data_inicial"))
    if not data_base:
        _snack(page, "Data inicial inválida.")
        return

    tenant_id = _get_tenant(page)
    if not tenant_id:
        _snack(page, "Tenant não identificado. Faça login novamente.")
        return

    partes_bd   = get_partes() or []
    vinculos_bd = get_vinculos(tenant_id) or []

    tf_cliente = ft.TextField(label="Cliente",
                              value=(contrato.get("clientes") or {}).get("nome", ""),
                              disabled=True, width=300)
    tf_nome_c  = ft.TextField(label="Contrato", value=contrato.get("nome"),
                              disabled=True, width=260)

    tf_resp = ft.TextField(
        label="Responsável",
        value=contrato.get("responsavel") or _get_usuario_nome(page),
        disabled=True, width=580,
    )

    tf_clausulas = ft.TextField(
        label="Observação / Cláusulas",
        value=contrato.get("clausulas") or "",
        width=580, multiline=True, min_lines=3, max_lines=5,
    )

    tf_data_ini = ft.TextField(label="Data inicial",
                               value=data_db_para_br(contrato.get("data_inicial")),
                               disabled=True, width=190)
    tf_data_ass = ft.TextField(label="Data de assinatura",
                               value=data_db_para_br(contrato.get("data_assinatura")),
                               width=190, read_only=True)
    tf_vig = ft.TextField(label="Vigência (meses)",
                          value=str(contrato.get("vigencia") or ""),
                          width=140, keyboard_type=ft.KeyboardType.NUMBER)
    tf_fim = ft.TextField(label="Termo final",
                          value=data_db_para_br(contrato.get("termo_final")),
                          width=190, read_only=True)

    def recalcular():
        if _is_int_str(tf_vig.value):
            tf_fim.value = data_db_para_br(_format_db(
                _data_por_meses(data_base, int(tf_vig.value))))
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

    # ---- prazos ----
    prazos           = get_prazos_por_contrato(contrato["id"]) or []
    container_prazos = ft.Column(spacing=6)
    linhas_prazos    = []
    excluir_prazos   = set()

    def criar_linha_prazo(pid, meses="", data="", obs="", existente=False):
        tf_m = ft.TextField(value=str(meses or ""), hint_text="Meses", width=80,
                            keyboard_type=ft.KeyboardType.NUMBER)
        tf_d = ft.TextField(value=data_db_para_br(data), width=130, read_only=True)
        tf_o = ft.TextField(value=obs or "", width=220)

        def sync():
            if _is_int_str(tf_m.value):
                tf_d.value = data_db_para_br(_format_db(
                    _data_por_meses(data_base, int(tf_m.value))))

        tf_m.on_change = lambda e: (sync(), page.update())

        def _set_data_prazo(d):
            tf_d.value = d.strftime("%d/%m/%Y")
            tf_m.value = str(_calcular_meses(data_base, d))
            page.update()

        def cal_p(e):
            calendario_ptbr(page, on_select=_set_data_prazo)

        def remover(e):
            container_prazos.controls.remove(row)
            if existente and pid:
                excluir_prazos.add(pid)
            page.update()

        row = ft.Row(
            [tf_m, tf_d,
             ft.OutlinedButton("Calendário", icon=ft.Icons.CALENDAR_TODAY,
                               height=32, on_click=cal_p),
             tf_o,
             ft.TextButton("X", on_click=remover)],
            spacing=6,
        )
        linhas_prazos.append((pid, tf_m, tf_d, tf_o))
        container_prazos.controls.append(row)

    for p in prazos:
        criar_linha_prazo(p["id"], p.get("meses"),
                          p.get("data_vencimento"),
                          p.get("observacao"), True)

    def novo_prazo(e):
        criar_linha_prazo(None)
        page.update()

    # ---- partes / anexos ----
    cp_existentes = get_contrato_partes(contrato["id"]) or []
    secao_partes  = _build_secao_partes(page, partes_bd, vinculos_bd, cp_existentes)

    anexos_existentes = list_anexos_storage(contrato["id"]) or []
    secao_anexos = _build_secao_anexos(page, modo="editar",
                                       anexos_existentes=anexos_existentes)

    def salvar(e):
        if tf_vig.value and not _is_int_str(tf_vig.value):
            _snack(page, "Vigência inválida.")
            return

        try:
            update_contrato(contrato["id"], {
                "responsavel":     tf_resp.value or "",
                "clausulas":       tf_clausulas.value or "",
                "data_assinatura": data_br_para_db(tf_data_ass.value) if tf_data_ass.value else None,
                "vigencia":        int(tf_vig.value) if _is_int_str(tf_vig.value) else None,
                "termo_final":     data_br_para_db(tf_fim.value),
            })

            for pid in excluir_prazos:
                update_prazo(pid, {"ativo": False})

            for pid, tf_m, tf_d, tf_o in linhas_prazos:
                if pid in excluir_prazos:
                    continue
                if not tf_m.value and not tf_d.value and not tf_o.value:
                    continue
                payload = {
                    "meses":           int(tf_m.value) if _is_int_str(tf_m.value) else None,
                    "data_vencimento": data_br_para_db(tf_d.value),
                    "observacao":      tf_o.value or "",
                }
                if pid:
                    update_prazo(pid, payload)
                else:
                    add_prazo(
                        contrato_id=contrato["id"],
                        meses=payload["meses"],
                        observacao=tf_o.value,
                        data_criacao=contrato.get("data_inicial"),
                        data_vencimento=payload["data_vencimento"],
                        tenant_id=tenant_id,
                    )

            for cp_id in secao_partes["excluir"]:
                delete_contrato_parte(cp_id)
            for ln in secao_partes["linhas"]:
                cp_id = ln["cp_id"]
                p_val = ln["dd_parte"].value
                t_val = ln["dd_tipo"].value
                if cp_id in secao_partes["excluir"] or not p_val or not t_val:
                    continue
                if cp_id is None:
                    add_contrato_parte(contrato["id"], int(p_val), t_val)

            # Anexos — exclusões e uploads no Storage privado "Heringer"
            for caminho in secao_anexos["excluir"]:
                delete_anexo_storage(caminho)
            picker_service = page.file_picker_service
            for arq in secao_anexos["pendentes"]:
                f = arq.get("_file")
                if f is None:
                    continue
                upload_list = [ft.FilePickerUploadFile(
                    name=f.name,
                    upload_url=page.get_upload_url(f.name, 60),
                )]
                picker_service.upload(upload_list)
                time.sleep(2)
                local_path = os.path.join(UPLOAD_DIR, f.name)
                try:
                    if os.path.exists(local_path):
                        with open(local_path, "rb") as fh:
                            data = fh.read()
                        upload_anexo_storage(contrato["id"], f.name, data)
                        _snack(page, f"Arquivo {f.name} enviado!")
                    else:
                        _snack(page, f"Arquivo {f.name} não encontrado no servidor")
                except Exception as ex:
                    _snack(page, f"Erro: {ex}")

        except Exception as ex:
            _snack(page, f"Erro: {ex}")
            return

        _fechar_dialog(page, dialog)
        on_save()
        _snack(page, "Contrato atualizado.")

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text(f"Editar — {contrato.get('nome', '')}"),
        content=ft.Container(
            height=660,
            content=ft.Column(
                [
                    ft.Row([tf_cliente, tf_nome_c], spacing=16, wrap=True),
                    secao_partes["widget"],
                    ft.Divider(height=1),
                    tf_resp,
                    tf_clausulas,
                    ft.Row([
                        ft.OutlinedButton("Assinatura", icon=ft.Icons.CALENDAR_TODAY,
                                          height=36, on_click=cal_ass),
                        tf_data_ass, tf_data_ini,
                    ], spacing=8, wrap=True),
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
                spacing=10, scroll=ft.ScrollMode.AUTO,
            ),
        ),
        actions=[
            ft.TextButton("Cancelar", on_click=lambda e: _fechar_dialog(page, dialog)),
            ft.FilledButton("Salvar", on_click=salvar),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    _abrir_dialog(page, dialog)


# ======================================================
# VER CONTRATO (somente leitura)
# ======================================================

def ver_contrato_dialog(page: ft.Page, contrato: dict, clientes_map: dict):

    prazos       = get_prazos_por_contrato(contrato["id"]) or []
    cp_lista     = get_contrato_partes(contrato["id"]) or []
    todas_partes = get_partes() or []
    partes_map   = {str(p["id"]): p for p in todas_partes}
    anexos       = list_anexos_storage(contrato["id"]) or []

    nome_cliente = clientes_map.get(contrato.get("cliente_id"), "-")

    if prazos:
        itens_prazos = [
            ft.Container(
                padding=ft.padding.symmetric(vertical=4, horizontal=8),
                border_radius=8, bgcolor=ft.Colors.GREY_50,
                border=ft.border.all(1, ft.Colors.GREY_200),
                content=ft.Row([
                    ft.Icon(ft.Icons.CALENDAR_TODAY, size=14, color=ft.Colors.BLUE_400),
                    ft.Text(data_db_para_br(p.get("data_vencimento")),
                            weight=ft.FontWeight.W_500, size=13),
                    ft.Text(f"— {p.get('observacao') or ''}",
                            color=ft.Colors.GREY_600, size=13),
                ], spacing=6),
            )
            for p in prazos
        ]
    else:
        itens_prazos = [ft.Text("Nenhum prazo cadastrado.",
                                color=ft.Colors.GREY_500, italic=True, size=13)]

    if cp_lista:
        itens_partes = [
            ft.Container(
                padding=ft.padding.symmetric(vertical=4, horizontal=8),
                border_radius=8, bgcolor=ft.Colors.GREY_50,
                border=ft.border.all(1, ft.Colors.GREY_200),
                content=ft.Row([
                    ft.Icon(ft.Icons.PERSON_OUTLINE, size=14, color=ft.Colors.BLUE_400),
                    ft.Text(
                        partes_map.get(str(cp.get("parte_id")), {}).get(
                            "nome", f"ID {cp.get('parte_id')}"),
                        weight=ft.FontWeight.W_500, size=13,
                    ),
                    ft.Text(f"— {cp.get('tipo_vinculo', '-')}",
                            color=ft.Colors.GREY_600, size=13),
                ], spacing=6),
            )
            for cp in cp_lista
        ]
    else:
        itens_partes = [ft.Text("Nenhuma parte vinculada.",
                                color=ft.Colors.GREY_500, italic=True, size=13)]

    secao_anexos = _build_secao_anexos(page, modo="ver", anexos_existentes=anexos)

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text(contrato.get("nome", ""), weight=ft.FontWeight.BOLD),
        content=ft.Container(
            height=540,
            content=ft.Column(
                [
                    ft.Text(f"Cliente: {nome_cliente}", size=13),
                    ft.Text(f"Responsável: {contrato.get('responsavel') or '-'}", size=13),
                    ft.Text(f"Assinatura: {data_db_para_br(contrato.get('data_assinatura'))}", size=13),
                    ft.Text(f"Início: {data_db_para_br(contrato.get('data_inicial'))}", size=13),
                    ft.Text(f"Vigência: {contrato.get('vigencia') or '-'} meses", size=13),
                    ft.Text(f"Fim: {data_db_para_br(contrato.get('termo_final'))}", size=13),
                    ft.Divider(),
                    ft.Text("Partes:", weight=ft.FontWeight.BOLD, size=13),
                    *itens_partes,
                    ft.Divider(),
                    ft.Text("Prazos:", weight=ft.FontWeight.BOLD, size=13),
                    *itens_prazos,
                    ft.Divider(),
                    secao_anexos["widget"],
                ],
                spacing=8, scroll=ft.ScrollMode.AUTO,
            ),
        ),
        actions=[ft.TextButton("Fechar", on_click=lambda e: _fechar_dialog(page, dialog))],
    )

    _abrir_dialog(page, dialog)