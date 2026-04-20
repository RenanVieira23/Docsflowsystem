import flet as ft
import os
import asyncio
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
    get_tipos_partes,
    get_contrato_partes,
    add_contrato_parte,
    delete_contrato_parte,
    get_usuarios,
    get_anexos_por_contrato,
    upload_anexo,
    delete_anexo,
)

from utils.calendario_ptbr import calendario_ptbr
from utils.dataptbr import data_br_para_db, data_db_para_br


DB_FMT = "%Y-%m-%d"
UPLOAD_DIR = os.environ.get("FLET_UPLOAD_DIR", "/tmp/flet_uploads")


# ======================================================
# HELPERS GERAIS
# ======================================================

def _snack(page: ft.Page, msg: str):
    page.snack_bar = ft.SnackBar(ft.Text(msg))
    page.snack_bar.open = True
    page.update()


def _parse_db(s: str):
    try:
        return datetime.strptime(s, DB_FMT)
    except:
        return None


def _format_db(dt):
    return dt.strftime(DB_FMT) if dt else ""


def _calcular_meses(data_base: datetime, data: datetime):
    return (data.year - data_base.year) * 12 + (data.month - data_base.month)


def _data_por_meses(data_base: datetime, meses: int):
    return data_base + relativedelta(months=meses)


def _gerar_nome(sigla: str, contratos: list):
    max_num = 0
    for c in contratos or []:
        nome = (c.get("nome") or "").strip()
        if not nome.startswith(sigla):
            continue
        suf = nome.replace(sigla, "", 1)
        if suf.isdigit():
            max_num = max(max_num, int(suf))
    return f"{sigla}{max_num + 1:04d}"


def _icone_extensao(nome: str) -> str:
    ext = nome.lower().rsplit(".", 1)[-1] if "." in nome else ""
    icones = {
        "pdf": ft.Icons.PICTURE_AS_PDF,
        "doc": ft.Icons.DESCRIPTION, "docx": ft.Icons.DESCRIPTION,
        "xls": ft.Icons.TABLE_CHART, "xlsx": ft.Icons.TABLE_CHART,
        "png": ft.Icons.IMAGE, "jpg": ft.Icons.IMAGE, "jpeg": ft.Icons.IMAGE,
        "gif": ft.Icons.IMAGE, "webp": ft.Icons.IMAGE,
        "zip": ft.Icons.FOLDER_ZIP, "txt": ft.Icons.TEXT_SNIPPET,
    }
    return icones.get(ext, ft.Icons.ATTACH_FILE)


# ======================================================
# SEÇÃO DE PARTES (reutilizável)
# ======================================================

def _build_secao_partes(page, partes_bd, tipos_bd, cp_existentes=None):
    opcoes_partes = [ft.dropdown.Option(str(p["id"]), p["nome"]) for p in (partes_bd or [])]
    opcoes_tipos  = [ft.dropdown.Option(t["nome"]) for t in (tipos_bd or [])]

    container = ft.Column(spacing=6)
    linhas    = []
    excluir   = set()

    def criar_linha(cp_id=None, parte_id=None, tipo_vinculo=None):
        dd_parte = ft.Dropdown(
            options=opcoes_partes, value=str(parte_id) if parte_id else None,
            hint_text="Selecionar parte", width=240, dense=True,
        )
        dd_tipo = ft.Dropdown(
            options=opcoes_tipos, value=tipo_vinculo,
            hint_text="Tipo de vínculo", width=180, dense=True,
        )

        def remover(e):
            container.controls.remove(row)
            if cp_id:
                excluir.add(cp_id)
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
                               icon_size=18, tooltip="Remover", on_click=remover)],
                spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )
        item = {"cp_id": cp_id, "dd_parte": dd_parte, "dd_tipo": dd_tipo}
        linhas.append(item)
        container.controls.append(row)

    for cp in (cp_existentes or []):
        criar_linha(cp_id=cp.get("id"), parte_id=cp.get("parte_id"), tipo_vinculo=cp.get("tipo_vinculo"))

    def nova_linha(e):
        criar_linha()
        page.update()

    avisos = []
    if not partes_bd:
        avisos.append("⚠️  Cadastre partes no menu 'Partes' antes de vincular.")
    if not tipos_bd:
        avisos.append("⚠️  Cadastre tipos no menu 'Tipos de Partes' antes de vincular.")

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
# ======================================================

def _build_secao_anexos(page: ft.Page, modo: str, anexos_existentes: list | None = None):
    """
    modo: "novo"   → só upload (salvo depois, quando contrato_id for conhecido)
          "editar" → upload de novos + remoção de existentes
          "ver"    → só visualização / download

    Retorna dict:
      widget         : ft.Column para inserir no dialog
      pendentes      : list[dict{"nome", "bytes"}]  — arquivos a fazer upload
      excluir        : list[dict{"id", "path"}]     — registros a deletar
      picker         : ft.FilePicker (já adicionado ao page.overlay)
    """

    pendentes = []
    excluir   = []

    lista_ui  = ft.Column(spacing=6)
    lbl_info  = ft.Text("", size=12, color=ft.Colors.GREY_500, italic=True)
    lbl_erro  = ft.Text("", size=12, color=ft.Colors.RED_700)

    # ---- Linha de arquivo existente ----
    def _linha_existente(a: dict):
        nome = a.get("nome_arquivo") or "Arquivo"
        url  = a.get("arquivo_url") or ""

        def _baixar(e, u=url):
            if u:
                page.launch_url(u)
            else:
                _snack(page, "URL não disponível para este arquivo.")

        btn_baixar = ft.TextButton(
            "Baixar",
            icon=ft.Icons.DOWNLOAD_OUTLINED,
            on_click=_baixar,
            style=ft.ButtonStyle(color=ft.Colors.BLUE_700),
        )

        botoes = [btn_baixar]

        if modo == "editar":
            def _remover(e, aa=a):
                lista_ui.controls.remove(row)
                excluir.append({"id": aa["id"], "path": aa.get("arquivo_path") or ""})
                page.update()
            botoes.append(
                ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=ft.Colors.RED_400,
                              icon_size=18, tooltip="Remover anexo", on_click=_remover)
            )

        row = ft.Container(
            padding=ft.padding.symmetric(vertical=6, horizontal=10),
            border_radius=8, bgcolor=ft.Colors.GREY_50,
            border=ft.border.all(1, ft.Colors.GREY_200),
            content=ft.Row(
                [ft.Icon(_icone_extensao(nome), size=18, color=ft.Colors.BLUE_400),
                 ft.Text(nome, size=13, expand=True),
                 *botoes],
                spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )
        lista_ui.controls.append(row)

    # ---- Linha de arquivo pendente (ainda não salvo) ----
    def _linha_pendente(nome: str, idx: int):
        def _cancelar(e, i=idx):
            # Remove da lista de pendentes e da UI
            if i < len(pendentes):
                pendentes.pop(i)
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
                 ft.IconButton(icon=ft.Icons.CLOSE, icon_size=16, icon_color=ft.Colors.BLUE_400,
                               tooltip="Cancelar", on_click=_cancelar)],
                spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )
        lista_ui.controls.append(row)
        page.update()

    # ---- Preenche existentes ----
    for a in (anexos_existentes or []):
        _linha_existente(a)

    if not (anexos_existentes or []) and modo == "ver":
        lbl_info.value = "Nenhum anexo vinculado a este contrato."

    # ---- FilePicker (upload) ----
    picker = ft.FilePicker()

    if modo != "ver":
        # Handler: arquivo selecionado
        def on_pick(e: ft.FilePickerResultEvent):
            if not e.files:
                return
            lbl_erro.value = ""

            for f in e.files:
                if f.path:
                    # Desktop: lê direto
                    try:
                        with open(f.path, "rb") as fh:
                            file_bytes = fh.read()
                        idx = len(pendentes)
                        pendentes.append({"nome": f.name, "bytes": file_bytes})
                        _linha_pendente(f.name, idx)
                    except Exception as ex:
                        lbl_erro.value = f"Erro ao ler {f.name}: {ex}"
                        page.update()
                else:
                    # Web: upload via Flet server
                    try:
                        upload_url = page.get_upload_url(f.name, 120)
                        picker.upload([ft.FilePickerUploadFile(f.name, upload_url=upload_url)])
                        lbl_info.value = f"Enviando {f.name}..."
                        page.update()
                    except Exception as ex:
                        lbl_erro.value = f"Erro ao iniciar upload: {ex}"
                        page.update()

        # Handler: upload via Flet server concluído
        def on_upload(e: ft.FilePickerUploadEvent):
            if e.error:
                lbl_erro.value = f"Erro no upload: {e.error}"
                page.update()
                return

            if e.progress and e.progress < 1.0:
                lbl_info.value = f"Enviando {e.file_name}: {int(e.progress * 100)}%"
                page.update()
                return

            # Upload completo → lê do diretório temporário
            lbl_info.value = ""
            flet_path = os.path.join(UPLOAD_DIR, e.file_name)
            try:
                with open(flet_path, "rb") as fh:
                    file_bytes = fh.read()
                try:
                    os.remove(flet_path)
                except:
                    pass
                idx = len(pendentes)
                pendentes.append({"nome": e.file_name, "bytes": file_bytes})
                _linha_pendente(e.file_name, idx)
            except Exception as ex:
                lbl_erro.value = f"Erro ao processar {e.file_name}: {ex}"
                page.update()

        picker.on_result  = on_pick
        picker.on_upload  = on_upload

        page.overlay.append(picker)

        btn_adicionar = ft.FilledTonalButton(
            "Adicionar arquivo",
            icon=ft.Icons.UPLOAD_FILE,
            on_click=lambda e: picker.pick_files(allow_multiple=True),
        )
    else:
        btn_adicionar = ft.Container()  # modo ver: sem botão

    widget = ft.Column(
        [
            ft.Row(
                [ft.Text("Anexos", weight=ft.FontWeight.BOLD, size=14), btn_adicionar],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            lbl_info,
            lbl_erro,
            lista_ui,
        ],
        spacing=6,
    )

    return {"widget": widget, "pendentes": pendentes, "excluir": excluir, "picker": picker}


# ======================================================
# NOVO CONTRATO
# ======================================================

def novo_contrato_dialog(page: ft.Page, atualizar_lista):

    clientes  = get_clientes()
    partes_bd = get_partes()
    tipos_bd  = get_tipos_partes()

    if not clientes:
        _snack(page, "Nenhum cliente cadastrado.")
        return

    dd_cliente = ft.Dropdown(
        label="Cliente", width=400,
        options=[ft.dropdown.Option(str(c["id"]), c["nome"]) for c in clientes],
    )
    tf_valor = ft.TextField(label="Valor", width=400)
    tf_clausulas = ft.TextField(label="Cláusulas", width=400, multiline=True, min_lines=3, max_lines=6)

    _usuarios      = get_usuarios()
    _resp_id_atual = str(page.local_store.get("usuario_id", "")) if hasattr(page, "local_store") else None
    dd_resp = ft.Dropdown(
        label="Responsável", width=400,
        options=[ft.dropdown.Option(str(u["id"]), u["usuario"]) for u in _usuarios],
        value=_resp_id_atual if any(str(u["id"]) == _resp_id_atual for u in _usuarios) else None,
    )

    tf_vig = ft.TextField(label="Vigência (meses)", width=200, keyboard_type=ft.KeyboardType.NUMBER)
    tf_data_ini = ft.TextField(label="Data inicial (DD/MM/AAAA)", width=200, hint_text="Ex: 15/03/2026")
    tf_data_ass = ft.TextField(label="Data de assinatura (DD/MM/AAAA)", width=200, hint_text="Ex: 15/03/2026")
    tf_fim = ft.TextField(label="Termo final", read_only=True, width=200)

    def recalcular():
        dt = _parse_db(data_br_para_db(tf_data_ini.value))
        if not dt:
            tf_fim.value = ""
            return
        if tf_vig.value.isdigit():
            tf_fim.value = data_db_para_br(_format_db(_data_por_meses(dt, int(tf_vig.value))))

    def escolher_data(e):
        calendario_ptbr(page, on_select=lambda d: (
            setattr(tf_data_ini, "value", d.strftime("%d/%m/%Y")), recalcular(), page.update()))

    def escolher_data_ass(e):
        calendario_ptbr(page, on_select=lambda d: (
            setattr(tf_data_ass, "value", d.strftime("%d/%m/%Y")), page.update()))

    tf_vig.on_change      = lambda e: (recalcular(), page.update())
    tf_data_ini.on_change = lambda e: (recalcular(), page.update())

    secao_partes = _build_secao_partes(page, partes_bd, tipos_bd)
    secao_anexos = _build_secao_anexos(page, modo="novo")

    # ---- SALVAR ----
    def salvar(e):
        if not dd_cliente.value or not tf_data_ini.value:
            _snack(page, "Cliente e data são obrigatórios.")
            return
        if not data_br_para_db(tf_data_ini.value):
            _snack(page, "Data inválida. Use DD/MM/AAAA.")
            return
        if tf_vig.value and not tf_vig.value.isdigit():
            _snack(page, "Vigência inválida.")
            return

        cli = next(c for c in clientes if str(c["id"]) == dd_cliente.value)
        nome = _gerar_nome(cli["sigla"], get_contratos_por_cliente(cli["id"]))

        try:
            novo = add_contrato({
                "nome": nome,
                "cliente_id": cli["id"],
                "valor": tf_valor.value,
                "clausulas": tf_clausulas.value,
                "responsavel": next(
                    (u["usuario"] for u in _usuarios if str(u["id"]) == (dd_resp.value or "")), ""),
                "data_inicial":   data_br_para_db(tf_data_ini.value),
                "data_assinatura": data_br_para_db(tf_data_ass.value) if tf_data_ass.value else None,
                "vigencia":   int(tf_vig.value) if tf_vig.value else None,
                "termo_final": data_br_para_db(tf_fim.value),
            })
        except Exception as ex:
            _snack(page, f"Erro: {ex}")
            return

        if novo:
            # Partes
            for linha in secao_partes["linhas"]:
                if linha["dd_parte"].value and linha["dd_tipo"].value:
                    add_contrato_parte(novo["id"], int(linha["dd_parte"].value), linha["dd_tipo"].value)

            # Anexos pendentes
            for arq in secao_anexos["pendentes"]:
                upload_anexo(novo["id"], arq["nome"], arq["bytes"])

        dialog.open = False
        atualizar_lista()
        _snack(page, f"Contrato {nome} criado.")

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Novo Contrato"),
        content=ft.Container(
            height=560,
            content=ft.Column(
                [
                    dd_cliente, tf_valor, tf_clausulas, dd_resp,
                    ft.Row([
                        ft.OutlinedButton("Calendário",           on_click=escolher_data),
                        ft.OutlinedButton("Calendário assinatura", on_click=escolher_data_ass),
                        tf_data_ass,
                        tf_data_ini,
                    ]),
                    ft.Row([tf_vig, tf_fim]),
                    ft.Divider(),
                    secao_partes["widget"],
                    ft.Divider(),
                    secao_anexos["widget"],
                ],
                spacing=10, scroll=ft.ScrollMode.AUTO,
            ),
        ),
        actions=[
            ft.TextButton("Cancelar", on_click=lambda e: setattr(dialog, "open", False)),
            ft.FilledButton("Salvar", on_click=salvar),
        ],
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
        _snack(page, "Data inicial inválida.")
        return

    tf_cliente = ft.TextField(label="Cliente", value=contrato.get("clientes", {}).get("nome", ""),
                              disabled=True, width=400)
    tf_nome    = ft.TextField(label="Contrato", value=contrato.get("nome"), disabled=True, width=400)
    tf_valor   = ft.TextField(label="Valor", value=str(contrato.get("valor") or ""), width=400)

    _usuarios       = get_usuarios()
    _resp_nome      = contrato.get("responsavel") or ""
    _resp_id        = next((str(u["id"]) for u in _usuarios if u["usuario"] == _resp_nome), None)
    dd_resp = ft.Dropdown(
        label="Responsável", width=400,
        options=[ft.dropdown.Option(str(u["id"]), u["usuario"]) for u in _usuarios],
        value=_resp_id,
    )

    tf_data_ini = ft.TextField(label="Data inicial",
                               value=data_db_para_br(contrato.get("data_inicial")),
                               disabled=True, width=200)
    tf_data_ass = ft.TextField(label="Data de assinatura",
                               value=data_db_para_br(contrato.get("data_assinatura")), width=200)
    tf_vig = ft.TextField(label="Vigência (meses)", value=str(contrato.get("vigencia") or ""),
                          width=200, keyboard_type=ft.KeyboardType.NUMBER)
    tf_fim = ft.TextField(label="Termo final", value=data_db_para_br(contrato.get("termo_final")),
                          width=200, read_only=True)

    def recalcular():
        if tf_vig.value.isdigit():
            tf_fim.value = data_db_para_br(_format_db(_data_por_meses(data_base, int(tf_vig.value))))
        else:
            tf_fim.value = ""
        page.update()

    def escolher_data_ass(e):
        calendario_ptbr(page, on_select=lambda d: (
            setattr(tf_data_ass, "value", d.strftime("%d/%m/%Y")), page.update()))

    tf_vig.on_change = lambda e: recalcular()
    recalcular()

    # ---- Prazos ----
    prazos = get_prazos_por_contrato(contrato["id"]) or []
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

        def escolher(e):
            calendario_ptbr(page, on_select=lambda d: (
                setattr(tf_d, "value", d.strftime("%d/%m/%Y")),
                setattr(tf_m, "value", str(_calcular_meses(data_base, d))),
                page.update()))

        def remover(e):
            container_prazos.controls.remove(row)
            if existente and pid:
                excluir_prazos.add(pid)
            page.update()

        row = ft.Row([tf_m, tf_d, ft.OutlinedButton("Calendário", on_click=escolher),
                      tf_o, ft.TextButton("X", on_click=remover)], spacing=6)
        linhas_prazos.append((pid, tf_m, tf_d, tf_o))
        container_prazos.controls.append(row)

    for p in prazos:
        criar_linha_prazo(p["id"], p.get("meses"), p.get("data_vencimento"), p.get("observacao"), True)

    def novo_prazo(e):
        criar_linha_prazo(None)
        page.update()

    # ---- Partes ----
    partes_bd    = get_partes()
    tipos_bd     = get_tipos_partes()
    cp_existentes = get_contrato_partes(contrato["id"])
    secao_partes = _build_secao_partes(page, partes_bd, tipos_bd, cp_existentes)

    # ---- Anexos ----
    anexos_existentes = get_anexos_por_contrato(contrato["id"])
    secao_anexos = _build_secao_anexos(page, modo="editar", anexos_existentes=anexos_existentes)

    # ---- SALVAR ----
    def salvar(e):
        if tf_vig.value and not tf_vig.value.isdigit():
            _snack(page, "Vigência inválida.")
            return

        try:
            update_contrato(contrato["id"], {
                "valor": tf_valor.value,
                "responsavel": next(
                    (u["usuario"] for u in _usuarios if str(u["id"]) == (dd_resp.value or "")), ""),
                "data_assinatura": data_br_para_db(tf_data_ass.value) if tf_data_ass.value else None,
                "vigencia":   int(tf_vig.value) if tf_vig.value else None,
                "termo_final": data_br_para_db(tf_fim.value),
            })

            # Prazos
            for pid in excluir_prazos:
                update_prazo(pid, {"ativo": False})
            for pid, tf_m, tf_d, tf_o in linhas_prazos:
                if pid in excluir_prazos:
                    continue
                if not tf_m.value and not tf_d.value and not tf_o.value:
                    continue
                payload = {
                    "meses":          int(tf_m.value) if tf_m.value.isdigit() else None,
                    "data_vencimento": data_br_para_db(tf_d.value),
                    "observacao":      tf_o.value or "",
                }
                if pid:
                    update_prazo(pid, payload)
                else:
                    add_prazo(contrato_id=contrato["id"], meses=payload["meses"],
                              observacao=tf_o.value, data_criacao=contrato["data_inicial"],
                              data_vencimento=payload["data_vencimento"])

            # Partes
            for cp_id in secao_partes["excluir"]:
                delete_contrato_parte(cp_id)
            for linha in secao_partes["linhas"]:
                cp_id = linha["cp_id"]
                p_val = linha["dd_parte"].value
                t_val = linha["dd_tipo"].value
                if cp_id in secao_partes["excluir"] or not p_val or not t_val:
                    continue
                if cp_id is None:
                    add_contrato_parte(contrato["id"], int(p_val), t_val)

            # Anexos — remove excluídos
            for item in secao_anexos["excluir"]:
                delete_anexo(item["id"], item["path"])

            # Anexos — upload novos
            for arq in secao_anexos["pendentes"]:
                upload_anexo(contrato["id"], arq["nome"], arq["bytes"])

        except Exception as ex:
            _snack(page, f"Erro: {ex}")
            return

        dialog.open = False
        on_save()
        _snack(page, "Contrato atualizado.")

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text(f"Editar {contrato['nome']}"),
        content=ft.Container(
            height=660,
            content=ft.Column(
                [
                    tf_cliente, tf_nome, tf_valor, dd_resp,
                    ft.Row([ft.OutlinedButton("Calendário assinatura", on_click=escolher_data_ass),
                            tf_data_ass]),
                    ft.Row([tf_data_ini]),
                    ft.Row([tf_vig, tf_fim]),
                    ft.Divider(),
                    ft.Row([ft.Text("Prazos", weight=ft.FontWeight.BOLD),
                            ft.FilledButton("Adicionar", on_click=novo_prazo)],
                           alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    container_prazos,
                    ft.Divider(),
                    secao_partes["widget"],
                    ft.Divider(),
                    secao_anexos["widget"],
                ],
                spacing=10, scroll=ft.ScrollMode.AUTO,
            ),
        ),
        actions=[
            ft.TextButton("Cancelar", on_click=lambda e: setattr(dialog, "open", False)),
            ft.FilledButton("Salvar", on_click=salvar),
        ],
    )

    page.overlay.append(dialog)
    dialog.open = True
    page.update()


# ======================================================
# VER CONTRATO (somente leitura)
# ======================================================

def ver_contrato_dialog(page: ft.Page, contrato: dict, clientes_map: dict):

    prazos    = get_prazos_por_contrato(contrato["id"]) or []
    cp_lista  = get_contrato_partes(contrato["id"]) or []
    todas_partes = get_partes() or []
    partes_map   = {str(p["id"]): p for p in todas_partes}
    anexos    = get_anexos_por_contrato(contrato["id"]) or []

    nome_cliente = clientes_map.get(contrato.get("cliente_id"), "-")

    # ---- Prazos ----
    if prazos:
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
        ]
    else:
        itens_prazos = [ft.Text("Nenhum prazo cadastrado.", color=ft.Colors.GREY_500, italic=True, size=13)]

    # ---- Partes ----
    if cp_lista:
        itens_partes = [
            ft.Container(
                padding=ft.padding.symmetric(vertical=4, horizontal=8),
                border_radius=8, bgcolor=ft.Colors.GREY_50,
                border=ft.border.all(1, ft.Colors.GREY_200),
                content=ft.Row([
                    ft.Icon(ft.Icons.PERSON_OUTLINE, size=14, color=ft.Colors.BLUE_400),
                    ft.Text(
                        partes_map.get(str(cp.get("parte_id")), {}).get("nome", f"ID {cp.get('parte_id')}"),
                        weight=ft.FontWeight.W_500, size=13,
                    ),
                    ft.Text(f"— {cp.get('tipo_vinculo', '-')}", color=ft.Colors.GREY_600, size=13),
                ], spacing=6),
            )
            for cp in cp_lista
        ]
    else:
        itens_partes = [ft.Text("Nenhuma parte vinculada.", color=ft.Colors.GREY_500, italic=True, size=13)]

    # ---- Anexos (somente visualização / download) ----
    secao_anexos = _build_secao_anexos(page, modo="ver", anexos_existentes=anexos)

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text(contrato.get("nome", ""), weight=ft.FontWeight.BOLD),
        content=ft.Container(
            height=520,
            content=ft.Column(
                [
                    ft.Text(f"Cliente: {nome_cliente}", size=13),
                    ft.Text(f"Responsável: {contrato.get('responsavel') or '-'}", size=13),
                    ft.Text(f"Valor: {contrato.get('valor') or '-'}", size=13),
                    ft.Text(f"Assinatura: {data_db_para_br(contrato.get('data_assinatura'))}", size=13),
                    ft.Text(f"Início: {data_db_para_br(contrato.get('data_inicial'))}", size=13),
                    ft.Text(f"Vigência: {contrato.get('vigencia') or '-'} meses", size=13),
                    ft.Text(f"Fim: {data_db_para_br(contrato.get('termo_final'))}", size=13),

                    ft.Divider(),
                    ft.Text("Partes do Contrato:", weight=ft.FontWeight.BOLD, size=13),
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