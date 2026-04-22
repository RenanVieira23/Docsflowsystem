"""
pages/contratos/form.py
========================
Correções nesta versão:
  1. FilePicker: criado e registrado (page.overlay + page.update) ANTES do dialog abrir
  2. Botão "Abrir" usa url= nativo do Flet (mais confiável que page.launch_url em web)
  3. Tipos de partes via tabela vinculos (get_vinculos, multi-tenant)
  4. tenant_id passado em get_clientes, get_contratos_por_cliente e add_contrato
  5. Responsável: TextField read-only com usuário logado (sem dropdown/get_usuarios)
"""
import flet as ft
import os
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
    get_vinculos,             # ← vinculos no lugar de tipos_partes
    get_contrato_partes,
    add_contrato_parte,
    delete_contrato_parte,
    get_anexos_por_contrato,
    upload_anexo,
    delete_anexo,
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

def _parse_db(s):
    try:    return datetime.strptime(s, DB_FMT)
    except: return None

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
            if suf.isdigit(): mx = max(mx, int(suf))
    return f"{sigla}{mx + 1:04d}"

def _icone_extensao(nome):
    ext = nome.lower().rsplit(".", 1)[-1] if "." in nome else ""
    m = {
        "pdf": ft.Icons.PICTURE_AS_PDF,
        "doc": ft.Icons.DESCRIPTION, "docx": ft.Icons.DESCRIPTION,
        "xls": ft.Icons.TABLE_CHART, "xlsx": ft.Icons.TABLE_CHART,
        "png": ft.Icons.IMAGE, "jpg": ft.Icons.IMAGE, "jpeg": ft.Icons.IMAGE,
        "zip": ft.Icons.FOLDER_ZIP, "txt": ft.Icons.TEXT_SNIPPET,
    }
    return m.get(ext, ft.Icons.ATTACH_FILE)

def _get_tenant(page):
    return page.local_store.get("tenant_id") if hasattr(page, "local_store") else None


# ======================================================
# SEÇÃO DE PARTES (usa vinculos)
# ======================================================

def _build_secao_partes(page, partes_bd, vinculos_bd, cp_existentes=None):
    """
    vinculos_bd: lista de dicts da tabela vinculos (campo "tipo").
    """
    opts_partes   = [ft.dropdown.Option(str(p["id"]), p["nome"]) for p in (partes_bd or [])]
    opts_vinculos = [ft.dropdown.Option(v["tipo"])               for v in (vinculos_bd or [])]

    container = ft.Column(spacing=6)
    linhas    = []
    excluir   = set()

    def criar_linha(cp_id=None, parte_id=None, tipo_vinculo=None):
        dd_parte = ft.Dropdown(options=opts_partes, value=str(parte_id) if parte_id else None,
                               hint_text="Selecionar parte", width=240, dense=True)
        dd_tipo  = ft.Dropdown(options=opts_vinculos, value=tipo_vinculo,
                               hint_text="Tipo de vínculo",  width=180, dense=True)

        def remover(e):
            container.controls.remove(row)
            if cp_id: excluir.add(cp_id)
            linhas.remove(item)
            page.update()

        row = ft.Container(
            padding=ft.padding.symmetric(vertical=4, horizontal=8),
            border_radius=8, bgcolor=ft.Colors.GREY_50,
            border=ft.border.all(1, ft.Colors.GREY_200),
            content=ft.Row(
                [ft.Icon(ft.Icons.PERSON_OUTLINE, size=16, color=ft.Colors.BLUE_400),
                 dd_parte, dd_tipo,
                 ft.IconButton(icon=ft.Icons.REMOVE_CIRCLE_OUTLINE, icon_color=ft.Colors.RED_400,
                               icon_size=18, on_click=remover)],
                spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )
        item = {"cp_id": cp_id, "dd_parte": dd_parte, "dd_tipo": dd_tipo}
        linhas.append(item); container.controls.append(row)

    for cp in (cp_existentes or []):
        criar_linha(cp_id=cp.get("id"), parte_id=cp.get("parte_id"),
                    tipo_vinculo=cp.get("tipo_vinculo"))

    def nova_linha(e):
        criar_linha(); page.update()

    avisos = []
    if not partes_bd:
        avisos.append("⚠️  Cadastre partes no menu 'Partes' antes de vincular.")
    if not vinculos_bd:
        avisos.append("⚠️  Cadastre tipos em Tipos → Tipos de Partes antes de vincular.")

    widget = ft.Column(
        [ft.Row([ft.Text("Partes", weight=ft.FontWeight.BOLD, size=14),
                 ft.FilledTonalButton("Adicionar parte", icon=ft.Icons.ADD, on_click=nova_linha)],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
         *[ft.Text(a, color=ft.Colors.ORANGE_700, size=12) for a in avisos],
         container],
        spacing=8,
    )
    return {"widget": widget, "linhas": linhas, "excluir": excluir}


# ======================================================
# SEÇÃO DE ANEXOS
# CORREÇÃO PRINCIPAL: picker passado como parâmetro (já registrado antes de abrir o dialog)
# ======================================================

def _build_secao_anexos(page, modo, picker=None, anexos_existentes=None):
    """
    modo   : "novo" | "editar" | "ver"
    picker : ft.FilePicker já em page.overlay e page.update() já chamado.
             None para modo "ver".
    """
    pendentes = []
    excluir   = []
    lista_ui  = ft.Column(spacing=6)
    lbl_prog  = ft.Text("", size=12, color=ft.Colors.BLUE_600)
    lbl_erro  = ft.Text("", size=12, color=ft.Colors.RED_700)

    # ── linha existente ──────────────────────────────────────
    def _row_existente(a):
        nome = a.get("nome_arquivo") or "Arquivo"
        url  = a.get("arquivo_url") or ""

        # Usa url= nativo do Flet para abrir no navegador — mais confiável que page.launch_url()
        btn_abrir = ft.ElevatedButton(
            content=ft.Row([
                ft.Icon(ft.Icons.OPEN_IN_NEW, size=14),
                ft.Text("Abrir", size=12),
            ], spacing=4, tight=True),
            url=url if url else None,
            url_target="_blank",
            style=ft.ButtonStyle(
                padding=ft.padding.symmetric(horizontal=10, vertical=6),
                color=ft.Colors.BLUE_700,
            ),
            disabled=not bool(url),
        )

        botoes = [btn_abrir]
        if modo == "editar":
            def _rm(e, aa=a):
                lista_ui.controls.remove(row)
                excluir.append({"id": aa["id"], "path": aa.get("arquivo_path") or ""})
                page.update()
            botoes.append(
                ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_size=18,
                              icon_color=ft.Colors.RED_400, on_click=_rm))

        row = ft.Container(
            padding=ft.padding.symmetric(vertical=6, horizontal=10),
            border_radius=8, bgcolor=ft.Colors.GREY_50,
            border=ft.border.all(1, ft.Colors.GREY_200),
            content=ft.Row(
                [ft.Icon(_icone_extensao(nome), size=18, color=ft.Colors.BLUE_400),
                 ft.Text(nome, size=13, expand=True), *botoes],
                spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )
        lista_ui.controls.append(row)

    # ── linha pendente ───────────────────────────────────────
    _idx_counter = [0]

    def _row_pendente(nome):
        cur_idx = _idx_counter[0]; _idx_counter[0] += 1

        def _cancel(e, ci=cur_idx):
            for j, p in enumerate(pendentes):
                if p.get("_idx") == ci:
                    pendentes.pop(j); break
            lista_ui.controls.remove(row)
            page.update()

        row = ft.Container(
            padding=ft.padding.symmetric(vertical=6, horizontal=10),
            border_radius=8, bgcolor=ft.Colors.BLUE_50,
            border=ft.border.all(1, ft.Colors.BLUE_100),
            content=ft.Row(
                [ft.Icon(_icone_extensao(nome), size=18, color=ft.Colors.BLUE_600),
                 ft.Text(nome, size=13, expand=True),
                 ft.Text("Pendente", size=11, color=ft.Colors.BLUE_600, italic=True),
                 ft.IconButton(icon=ft.Icons.CLOSE, icon_size=16,
                               icon_color=ft.Colors.BLUE_400, on_click=_cancel)],
                spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )
        lista_ui.controls.append(row)
        page.update()
        return cur_idx

    # ── preenche existentes ──────────────────────────────────
    for a in (anexos_existentes or []):
        _row_existente(a)

    if not (anexos_existentes or []) and modo == "ver":
        lbl_prog.value = "Nenhum anexo vinculado a este contrato."

    # ── handlers do picker (só nos modos novo/editar) ────────
    if picker and modo != "ver":
        def on_result(e: ft.FilePickerResultEvent):
            if not e.files: return
            lbl_erro.value = ""
            for f in e.files:
                if f.path:
                    # Desktop: lê direto
                    try:
                        with open(f.path, "rb") as fh: data = fh.read()
                        idx = _row_pendente(f.name)
                        pendentes.append({"nome": f.name, "bytes": data, "_idx": idx})
                    except Exception as ex:
                        lbl_erro.value = f"Erro: {ex}"; page.update()
                else:
                    # Web: Flet upload server
                    try:
                        url = page.get_upload_url(f.name, 120)
                        picker.upload([ft.FilePickerUploadFile(f.name, upload_url=url)])
                        lbl_prog.value = f"Enviando {f.name}..."
                        page.update()
                    except Exception as ex:
                        lbl_erro.value = f"Erro upload: {ex}"; page.update()

        def on_upload(e: ft.FilePickerUploadEvent):
            if e.error:
                lbl_erro.value = f"Erro: {e.error}"; page.update(); return
            if e.progress and e.progress < 1.0:
                lbl_prog.value = f"Enviando {e.file_name}: {int(e.progress*100)}%"
                page.update(); return
            lbl_prog.value = ""
            path = os.path.join(UPLOAD_DIR, e.file_name)
            try:
                with open(path, "rb") as fh: data = fh.read()
                try: os.remove(path)
                except: pass
                idx = _row_pendente(e.file_name)
                pendentes.append({"nome": e.file_name, "bytes": data, "_idx": idx})
            except Exception as ex:
                lbl_erro.value = f"Erro: {ex}"; page.update()

        picker.on_result = on_result
        picker.on_upload = on_upload

    btn_add = (
        ft.FilledTonalButton("Adicionar arquivo", icon=ft.Icons.UPLOAD_FILE,
                             on_click=lambda e: picker.pick_files(allow_multiple=True))
        if picker and modo != "ver"
        else ft.Container()
    )

    widget = ft.Column([
        ft.Row([ft.Text("Anexos", weight=ft.FontWeight.BOLD, size=14), btn_add],
               alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        lbl_prog, lbl_erro, lista_ui,
    ], spacing=6)

    return {"widget": widget, "pendentes": pendentes, "excluir": excluir}


# ======================================================
# NOVO CONTRATO
# ======================================================

def novo_contrato_dialog(page: ft.Page, atualizar_lista):

    tenant_id = _get_tenant(page)
    clientes  = get_clientes(tenant_id)

    if not clientes:
        _snack(page, "Nenhum cliente cadastrado.")
        return

    partes_bd   = get_partes()
    vinculos_bd = get_vinculos(tenant_id)

    # ── FilePicker: registrar ANTES do dialog ──────────────────
    picker = ft.FilePicker()
    page.overlay.append(picker)
    page.update()   # ← registra picker no cliente web
    # ──────────────────────────────────────────────────────────

    dd_cliente = ft.Dropdown(
        label="Cliente", width=380,
        options=[ft.dropdown.Option(str(c["id"]), c["nome"]) for c in clientes],
    )

    # Responsável read-only (usuário logado)
    _resp_nome = page.local_store.get("usuario_nome", "") if hasattr(page, "local_store") else ""
    tf_resp = ft.TextField(label="Responsável", value=_resp_nome, disabled=True, width=380)

    tf_clausulas = ft.TextField(
        label="Observação / Cláusulas", width=380,
        multiline=True, min_lines=3, max_lines=5,
    )

    tf_data_ini = ft.TextField(label="Data inicial (DD/MM/AAAA)", width=190, hint_text="Ex: 01/01/2025")
    tf_data_ass = ft.TextField(label="Data de assinatura",        width=190, hint_text="Ex: 01/01/2025")
    tf_vig      = ft.TextField(label="Vigência (meses)", width=140, keyboard_type=ft.KeyboardType.NUMBER)
    tf_fim      = ft.TextField(label="Termo final", read_only=True, width=190)

    def recalcular():
        dt = _parse_db(data_br_para_db(tf_data_ini.value))
        tf_fim.value = data_db_para_br(_format_db(_data_por_meses(dt, int(tf_vig.value)))) \
            if dt and tf_vig.value.isdigit() else ""

    def cal_ini(e):
        calendario_ptbr(page, on_select=lambda d: (
            setattr(tf_data_ini, "value", d.strftime("%d/%m/%Y")), recalcular(), page.update()))

    def cal_ass(e):
        calendario_ptbr(page, on_select=lambda d: (
            setattr(tf_data_ass, "value", d.strftime("%d/%m/%Y")), page.update()))

    tf_vig.on_change      = lambda e: (recalcular(), page.update())
    tf_data_ini.on_change = lambda e: (recalcular(), page.update())

    secao_partes = _build_secao_partes(page, partes_bd, vinculos_bd)
    secao_anexos = _build_secao_anexos(page, modo="novo", picker=picker)

    # ── salvar ────────────────────────────────────────────────
    def salvar(e):
        if not dd_cliente.value or not tf_data_ini.value:
            _snack(page, "Cliente e data inicial são obrigatórios."); return
        if not data_br_para_db(tf_data_ini.value):
            _snack(page, "Data inválida. Use DD/MM/AAAA."); return
        if tf_vig.value and not tf_vig.value.isdigit():
            _snack(page, "Vigência inválida."); return

        cli  = next(c for c in clientes if str(c["id"]) == dd_cliente.value)
        nome = _gerar_nome(cli["sigla"], get_contratos_por_cliente(cli["id"], tenant_id))

        try:
            novo = add_contrato({
                "nome":           nome,
                "cliente_id":     cli["id"],
                "tenant_id":      tenant_id,   # ← multi-tenant
                "responsavel":    tf_resp.value,
                "clausulas":      tf_clausulas.value,
                "data_inicial":   data_br_para_db(tf_data_ini.value),
                "data_assinatura": data_br_para_db(tf_data_ass.value) if tf_data_ass.value else None,
                "vigencia":       int(tf_vig.value) if tf_vig.value else None,
                "termo_final":    data_br_para_db(tf_fim.value),
            })
        except Exception as ex:
            _snack(page, f"Erro: {ex}"); return

        if novo:
            for ln in secao_partes["linhas"]:
                if ln["dd_parte"].value and ln["dd_tipo"].value:
                    add_contrato_parte(novo["id"], int(ln["dd_parte"].value), ln["dd_tipo"].value)
            for arq in secao_anexos["pendentes"]:
                upload_anexo(novo["id"], arq["nome"], arq["bytes"])

        dialog.open = False
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
                        ft.OutlinedButton("📅 Data inicial",    height=36, on_click=cal_ini), tf_data_ini,
                        ft.OutlinedButton("📅 Data assinatura", height=36, on_click=cal_ass), tf_data_ass,
                    ], spacing=8, wrap=True),
                    ft.Row([tf_vig, tf_fim], spacing=16),
                    ft.Divider(height=1),
                    secao_anexos["widget"],
                ],
                spacing=10, scroll=ft.ScrollMode.AUTO,
            ),
        ),
        actions=[
            ft.TextButton("Cancelar", on_click=lambda e: setattr(dialog, "open", False)),
            ft.FilledButton("Salvar", on_click=salvar),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    page.overlay.append(dialog)
    dialog.open = True
    page.update()


# ======================================================
# EDITAR CONTRATO
# ======================================================

def editar_contrato_dialog(page: ft.Page, contrato: dict, on_save):

    data_base = _parse_db(contrato.get("data_inicial"))
    if not data_base:
        _snack(page, "Data inicial inválida."); return

    tenant_id   = _get_tenant(page)
    partes_bd   = get_partes()
    vinculos_bd = get_vinculos(tenant_id)

    # ── FilePicker pré-registrado ──────────────────────────────
    picker = ft.FilePicker()
    page.overlay.append(picker)
    page.update()
    # ──────────────────────────────────────────────────────────

    tf_cliente  = ft.TextField(label="Cliente",   value=contrato.get("clientes", {}).get("nome", ""),
                               disabled=True, width=300)
    tf_nome_c   = ft.TextField(label="Contrato",  value=contrato.get("nome"), disabled=True, width=260)

    tf_resp = ft.TextField(
        label="Responsável",
        value=contrato.get("responsavel") or page.local_store.get("usuario_nome", ""),
        disabled=True, width=580,
    )

    tf_clausulas = ft.TextField(
        label="Observação / Cláusulas", value=contrato.get("clausulas") or "",
        width=580, multiline=True, min_lines=3, max_lines=5,
    )

    tf_data_ini = ft.TextField(label="Data inicial",
                               value=data_db_para_br(contrato.get("data_inicial")),
                               disabled=True, width=190)
    tf_data_ass = ft.TextField(label="Data de assinatura",
                               value=data_db_para_br(contrato.get("data_assinatura")), width=190)
    tf_vig = ft.TextField(label="Vigência (meses)", value=str(contrato.get("vigencia") or ""),
                          width=140, keyboard_type=ft.KeyboardType.NUMBER)
    tf_fim = ft.TextField(label="Termo final", value=data_db_para_br(contrato.get("termo_final")),
                          width=190, read_only=True)

    def recalcular():
        tf_fim.value = data_db_para_br(_format_db(_data_por_meses(data_base, int(tf_vig.value)))) \
            if tf_vig.value.isdigit() else ""
        page.update()

    def cal_ass(e):
        calendario_ptbr(page, on_select=lambda d: (
            setattr(tf_data_ass, "value", d.strftime("%d/%m/%Y")), page.update()))

    tf_vig.on_change = lambda e: recalcular()
    recalcular()

    # ── prazos ────────────────────────────────────────────────
    prazos           = get_prazos_por_contrato(contrato["id"]) or []
    container_prazos = ft.Column(spacing=6)
    linhas_prazos    = []
    excluir_prazos   = set()

    def criar_linha_prazo(pid, meses="", data="", obs="", existente=False):
        tf_m = ft.TextField(value=str(meses or ""), hint_text="Meses", width=80,
                            keyboard_type=ft.KeyboardType.NUMBER)
        tf_d = ft.TextField(value=data_db_para_br(data), width=130)
        tf_o = ft.TextField(value=obs or "", width=220)

        def sync():
            if tf_m.value.isdigit():
                tf_d.value = data_db_para_br(_format_db(_data_por_meses(data_base, int(tf_m.value))))

        tf_m.on_change = lambda e: (sync(), page.update())

        def cal_p(e):
            calendario_ptbr(page, on_select=lambda d: (
                setattr(tf_d, "value", d.strftime("%d/%m/%Y")),
                setattr(tf_m, "value", str(_calcular_meses(data_base, d))),
                page.update()))

        def remover(e):
            container_prazos.controls.remove(row)
            if existente and pid: excluir_prazos.add(pid)
            page.update()

        row = ft.Row([tf_m, tf_d,
                      ft.OutlinedButton("📅", height=32, on_click=cal_p,
                                        style=ft.ButtonStyle(padding=ft.padding.symmetric(horizontal=8))),
                      tf_o, ft.TextButton("×", on_click=remover)], spacing=6)
        linhas_prazos.append((pid, tf_m, tf_d, tf_o))
        container_prazos.controls.append(row)

    for p in prazos:
        criar_linha_prazo(p["id"], p.get("meses"), p.get("data_vencimento"), p.get("observacao"), True)

    def novo_prazo(e):
        criar_linha_prazo(None); page.update()

    # ── partes / anexos ───────────────────────────────────────
    cp_existentes     = get_contrato_partes(contrato["id"])
    secao_partes      = _build_secao_partes(page, partes_bd, vinculos_bd, cp_existentes)
    anexos_existentes = get_anexos_por_contrato(contrato["id"])
    secao_anexos      = _build_secao_anexos(page, modo="editar", picker=picker,
                                            anexos_existentes=anexos_existentes)

    # ── salvar ────────────────────────────────────────────────
    def salvar(e):
        if tf_vig.value and not tf_vig.value.isdigit():
            _snack(page, "Vigência inválida."); return
        try:
            update_contrato(contrato["id"], {
                "responsavel":    tf_resp.value,
                "clausulas":      tf_clausulas.value,
                "data_assinatura": data_br_para_db(tf_data_ass.value) if tf_data_ass.value else None,
                "vigencia":       int(tf_vig.value) if tf_vig.value else None,
                "termo_final":    data_br_para_db(tf_fim.value),
            })

            for pid in excluir_prazos:
                update_prazo(pid, {"ativo": False})
            for pid, tf_m, tf_d, tf_o in linhas_prazos:
                if pid in excluir_prazos: continue
                if not tf_m.value and not tf_d.value and not tf_o.value: continue
                payload = {
                    "meses":           int(tf_m.value) if tf_m.value.isdigit() else None,
                    "data_vencimento": data_br_para_db(tf_d.value),
                    "observacao":      tf_o.value or "",
                }
                if pid:
                    update_prazo(pid, payload)
                else:
                    add_prazo(contrato_id=contrato["id"], meses=payload["meses"],
                              observacao=tf_o.value, data_criacao=contrato.get("data_inicial"),
                              data_vencimento=payload["data_vencimento"])

            for cp_id in secao_partes["excluir"]:
                delete_contrato_parte(cp_id)
            for ln in secao_partes["linhas"]:
                cp_id = ln["cp_id"]; p_val = ln["dd_parte"].value; t_val = ln["dd_tipo"].value
                if cp_id in secao_partes["excluir"] or not p_val or not t_val: continue
                if cp_id is None:
                    add_contrato_parte(contrato["id"], int(p_val), t_val)

            for it in secao_anexos["excluir"]:
                delete_anexo(it["id"], it["path"])
            for arq in secao_anexos["pendentes"]:
                upload_anexo(contrato["id"], arq["nome"], arq["bytes"])

        except Exception as ex:
            _snack(page, f"Erro: {ex}"); return

        dialog.open = False
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
                        ft.OutlinedButton("📅 Assinatura", height=36, on_click=cal_ass),
                        tf_data_ass, tf_data_ini,
                    ], spacing=8, wrap=True),
                    ft.Row([tf_vig, tf_fim], spacing=16),
                    ft.Divider(height=1),
                    ft.Row([ft.Text("Prazos", weight=ft.FontWeight.BOLD),
                            ft.FilledButton("Adicionar prazo", height=32, on_click=novo_prazo)],
                           alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    container_prazos,
                    ft.Divider(height=1),
                    secao_anexos["widget"],
                ],
                spacing=10, scroll=ft.ScrollMode.AUTO,
            ),
        ),
        actions=[
            ft.TextButton("Cancelar", on_click=lambda e: setattr(dialog, "open", False)),
            ft.FilledButton("Salvar", on_click=salvar),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    page.overlay.append(dialog)
    dialog.open = True
    page.update()


# ======================================================
# VER CONTRATO (somente leitura — sem FilePicker)
# ======================================================

def ver_contrato_dialog(page: ft.Page, contrato: dict, clientes_map: dict):

    prazos       = get_prazos_por_contrato(contrato["id"]) or []
    cp_lista     = get_contrato_partes(contrato["id"]) or []
    todas_partes = get_partes() or []
    partes_map   = {str(p["id"]): p for p in todas_partes}
    anexos       = get_anexos_por_contrato(contrato["id"]) or []

    nome_cliente = clientes_map.get(contrato.get("cliente_id"), "-")

    itens_prazos = [
        ft.Container(
            padding=ft.padding.symmetric(vertical=4, horizontal=8),
            border_radius=8, bgcolor=ft.Colors.GREY_50,
            border=ft.border.all(1, ft.Colors.GREY_200),
            content=ft.Row([
                ft.Icon(ft.Icons.CALENDAR_TODAY, size=14, color=ft.Colors.BLUE_400),
                ft.Text(data_db_para_br(p.get("data_vencimento")), weight=ft.FontWeight.W_500, size=13),
                ft.Text(f"— {p.get('observacao') or ''}", color=ft.Colors.GREY_600, size=13),
            ], spacing=6),
        )
        for p in prazos
    ] or [ft.Text("Nenhum prazo cadastrado.", color=ft.Colors.GREY_500, italic=True, size=13)]

    itens_partes = [
        ft.Container(
            padding=ft.padding.symmetric(vertical=4, horizontal=8),
            border_radius=8, bgcolor=ft.Colors.GREY_50,
            border=ft.border.all(1, ft.Colors.GREY_200),
            content=ft.Row([
                ft.Icon(ft.Icons.PERSON_OUTLINE, size=14, color=ft.Colors.BLUE_400),
                ft.Text(partes_map.get(str(cp.get("parte_id")), {}).get("nome", f"ID {cp.get('parte_id')}"),
                        weight=ft.FontWeight.W_500, size=13),
                ft.Text(f"— {cp.get('tipo_vinculo', '-')}", color=ft.Colors.GREY_600, size=13),
            ], spacing=6),
        )
        for cp in cp_lista
    ] or [ft.Text("Nenhuma parte vinculada.", color=ft.Colors.GREY_500, italic=True, size=13)]

    # Anexos no modo "ver": picker=None, botão usa url=
    secao_anexos = _build_secao_anexos(page, modo="ver", picker=None, anexos_existentes=anexos)

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
        actions=[ft.TextButton("Fechar", on_click=lambda e: _fechar_ver(dialog, page))],
    )

    page.overlay.append(dialog)
    dialog.open = True
    page.update()


def _fechar_ver(dialog, page):
    dialog.open = False
    page.update()