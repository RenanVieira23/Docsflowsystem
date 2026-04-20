import flet as ft
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
    get_usuarios,
    get_contrato_partes,
    add_contrato_parte,
    delete_contrato_parte,
)

from utils.calendario_ptbr import calendario_ptbr
from utils.dataptbr import data_br_para_db, data_db_para_br


DB_FMT = "%Y-%m-%d"


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


# ======================================================
# SEÇÃO DE PARTES (reutilizável em novo e editar)
# ======================================================

def _build_secao_partes(page, partes_bd, tipos_bd, cp_existentes=None):
    """
    Retorna dict com:
      - "widget"   : ft.Column  → inserir no dialog
      - "linhas"   : list[dict] → cada linha tem cp_id, dd_parte, dd_tipo
      - "excluir"  : set[int]   → IDs de contrato_partes a deletar
    """

    opcoes_partes = [
        ft.dropdown.Option(str(p["id"]), p["nome"])
        for p in (partes_bd or [])
    ]

    opcoes_tipos = [
        ft.dropdown.Option(t["nome"])
        for t in (tipos_bd or [])
    ]

    container = ft.Column(spacing=6)
    linhas = []
    excluir = set()

    # --------------------------------------------------

    def criar_linha(cp_id=None, parte_id=None, tipo_vinculo=None):

        dd_parte = ft.Dropdown(
            options=opcoes_partes,
            value=str(parte_id) if parte_id else None,
            hint_text="Selecionar parte",
            width=240,
            dense=True,
        )

        dd_tipo = ft.Dropdown(
            options=opcoes_tipos,
            value=tipo_vinculo,
            hint_text="Tipo de vínculo",
            width=180,
            dense=True,
        )

        def remover(e):
            container.controls.remove(row)
            if cp_id:
                excluir.add(cp_id)
            linhas.remove(item)
            page.update()

        row = ft.Container(
            padding=ft.padding.symmetric(vertical=4, horizontal=8),
            border_radius=8,
            bgcolor=ft.Colors.GREY_50,
            border=ft.border.all(1, ft.Colors.GREY_200),
            content=ft.Row(
                [
                    ft.Icon(
                        ft.Icons.PERSON_OUTLINE,
                        size=16,
                        color=ft.Colors.BLUE_400,
                    ),
                    dd_parte,
                    dd_tipo,
                    ft.IconButton(
                        icon=ft.Icons.REMOVE_CIRCLE_OUTLINE,
                        icon_color=ft.Colors.RED_400,
                        icon_size=18,
                        tooltip="Remover",
                        on_click=remover,
                    ),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

        item = {"cp_id": cp_id, "dd_parte": dd_parte, "dd_tipo": dd_tipo}
        linhas.append(item)
        container.controls.append(row)

    # --------------------------------------------------
    # Preenche existentes
    for cp in (cp_existentes or []):
        criar_linha(
            cp_id=cp.get("id"),
            parte_id=cp.get("parte_id"),
            tipo_vinculo=cp.get("tipo_vinculo"),
        )

    def nova_linha(e):
        criar_linha()
        page.update()

    # Avisos se não há partes/tipos cadastrados
    avisos = []
    if not partes_bd:
        avisos.append("⚠️  Cadastre partes no menu 'Partes' antes de vincular.")
    if not tipos_bd:
        avisos.append("⚠️  Cadastre tipos no menu 'Tipos de Partes' antes de vincular.")

    widget = ft.Column(
        [
            ft.Row(
                [
                    ft.Text("Partes", weight=ft.FontWeight.BOLD, size=14),
                    ft.FilledTonalButton(
                        "Adicionar parte",
                        icon=ft.Icons.ADD,
                        on_click=nova_linha,
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            *[ft.Text(a, color=ft.Colors.ORANGE_700, size=12) for a in avisos],
            container,
        ],
        spacing=8,
    )

    return {"widget": widget, "linhas": linhas, "excluir": excluir}


# ======================================================
# NOVO CONTRATO
# ======================================================

def novo_contrato_dialog(page: ft.Page, atualizar_lista):

    clientes = get_clientes()
    partes_bd = get_partes()
    tipos_bd = get_tipos_partes()

    if not clientes:
        _snack(page, "Nenhum cliente cadastrado.")
        return

    dd_cliente = ft.Dropdown(
        label="Cliente",
        width=400,
        options=[ft.dropdown.Option(str(c["id"]), c["nome"]) for c in clientes],
    )

    tf_valor = ft.TextField(label="Valor", width=400)

    tf_clausulas = ft.TextField(
        label="Cláusulas",
        width=400,
        multiline=True,
        min_lines=3,
        max_lines=6,
    )

    _nome_usuario = page.local_store.get("usuario_nome", "") if hasattr(page, "local_store") else ""
    tf_resp = ft.TextField(label="Responsável", width=400, value=_nome_usuario)

    tf_vig = ft.TextField(
        label="Vigência (meses)",
        width=200,
        keyboard_type=ft.KeyboardType.NUMBER,
    )

    tf_data_ini = ft.TextField(
        label="Data inicial (DD/MM/AAAA)",
        width=200,
        hint_text="Ex: 15/03/2026",
    )

    tf_data_ass = ft.TextField(
        label="Data de assinatura (DD/MM/AAAA)",
        width=200,
        hint_text="Ex: 15/03/2026",
    )

    tf_fim = ft.TextField(label="Termo final", read_only=True, width=200)

    # -------------------------
    # CALENDÁRIOS
    # -------------------------

    def recalcular():
        data_db = data_br_para_db(tf_data_ini.value)
        dt = _parse_db(data_db)
        if not dt:
            tf_fim.value = ""
            return
        if tf_vig.value.isdigit():
            meses = int(tf_vig.value)
            tf_fim.value = data_db_para_br(_format_db(_data_por_meses(dt, meses)))

    def escolher_data(e):
        calendario_ptbr(
            page,
            on_select=lambda d: (
                setattr(tf_data_ini, "value", d.strftime("%d/%m/%Y")),
                recalcular(),
                page.update(),
            ),
        )

    def escolher_data_ass(e):
        calendario_ptbr(
            page,
            on_select=lambda d: (
                setattr(tf_data_ass, "value", d.strftime("%d/%m/%Y")),
                page.update(),
            ),
        )

    tf_vig.on_change = lambda e: (recalcular(), page.update())
    tf_data_ini.on_change = lambda e: (recalcular(), page.update())

    # -------------------------
    # SEÇÃO DE PARTES
    # -------------------------

    secao_partes = _build_secao_partes(page, partes_bd, tipos_bd)

    # -------------------------
    # SALVAR
    # -------------------------

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
        contratos = get_contratos_por_cliente(cli["id"])
        nome = _gerar_nome(cli["sigla"], contratos)

        try:
            novo = add_contrato({
                "nome": nome,
                "cliente_id": cli["id"],
                "valor": tf_valor.value,
                "clausulas": tf_clausulas.value,
                "responsavel": next((u["usuario"] for u in _usuarios if str(u["id"]) == (dd_resp.value or "")), dd_resp.value or ""),
                "data_inicial": data_br_para_db(tf_data_ini.value),
                "data_assinatura": data_br_para_db(tf_data_ass.value) if tf_data_ass.value else None,
                "vigencia": int(tf_vig.value) if tf_vig.value else None,
                "termo_final": data_br_para_db(tf_fim.value),
            })
        except Exception as ex:
            _snack(page, f"Erro: {ex}")
            return

        # Salvar partes vinculadas
        if novo:
            for linha in secao_partes["linhas"]:
                p_val = linha["dd_parte"].value
                t_val = linha["dd_tipo"].value
                if p_val and t_val:
                    add_contrato_parte(novo["id"], int(p_val), t_val)

        dialog.open = False
        atualizar_lista()
        _snack(page, f"Contrato {nome} criado.")

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Novo Contrato"),
        content=ft.Container(
            height=520,
            content=ft.Column(
                [
                    dd_cliente,
                    tf_valor,
                    tf_clausulas,
                    dd_resp,

                    ft.Row([
                        ft.OutlinedButton("Calendário", on_click=escolher_data),
                        ft.Row([
                            ft.OutlinedButton("Calendário assinatura", on_click=escolher_data_ass),
                            tf_data_ass,
                        ]),
                        tf_data_ini,
                    ]),

                    ft.Row([tf_vig, tf_fim]),

                    ft.Divider(),

                    secao_partes["widget"],
                ],
                spacing=10,
                scroll=ft.ScrollMode.AUTO,
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

    # -------------------------
    # CAMPOS
    # -------------------------

    tf_cliente = ft.TextField(
        label="Cliente",
        value=contrato.get("clientes", {}).get("nome", ""),
        disabled=True,
        width=400,
    )

    tf_nome = ft.TextField(
        label="Contrato",
        value=contrato.get("nome"),
        disabled=True,
        width=400,
    )

    tf_valor = ft.TextField(
        label="Valor",
        value=str(contrato.get("valor") or ""),
        width=400,
    )

    _usuarios = get_usuarios()
    _opcoes_resp = [
        ft.dropdown.Option(str(u["id"]), u["usuario"])
        for u in _usuarios
    ]
    # Tenta encontrar o usuário pelo nome salvo no contrato
    _resp_nome_atual = contrato.get("responsavel") or ""
    _resp_id_atual = next(
        (str(u["id"]) for u in _usuarios if u["usuario"] == _resp_nome_atual), None
    )
    dd_resp = ft.Dropdown(
        label="Responsável",
        width=400,
        options=_opcoes_resp,
        value=_resp_id_atual,
    )

    tf_data_ini = ft.TextField(
        label="Data inicial",
        value=data_db_para_br(contrato.get("data_inicial")),
        disabled=True,
        width=200,
    )

    tf_data_ass = ft.TextField(
        label="Data de assinatura",
        value=data_db_para_br(contrato.get("data_assinatura")),
        width=200,
    )

    tf_vig = ft.TextField(
        label="Vigência (meses)",
        value=str(contrato.get("vigencia") or ""),
        width=200,
        keyboard_type=ft.KeyboardType.NUMBER,
    )

    tf_fim = ft.TextField(
        label="Termo final",
        value=data_db_para_br(contrato.get("termo_final")),
        width=200,
        read_only=True,
    )

    def recalcular():
        if tf_vig.value.isdigit():
            meses = int(tf_vig.value)
            tf_fim.value = data_db_para_br(_format_db(_data_por_meses(data_base, meses)))
        else:
            tf_fim.value = ""
        page.update()

    def escolher_data_ass(e):
        calendario_ptbr(
            page,
            on_select=lambda d: (
                setattr(tf_data_ass, "value", d.strftime("%d/%m/%Y")),
                page.update(),
            ),
        )

    tf_vig.on_change = lambda e: recalcular()
    recalcular()

    # -------------------------
    # PRAZOS
    # -------------------------

    prazos = get_prazos_por_contrato(contrato["id"]) or []

    container_prazos = ft.Column(spacing=6)
    linhas_prazos = []
    excluir_prazos = set()

    def criar_linha_prazo(pid, meses="", data="", obs="", existente=False):

        tf_m = ft.TextField(
            value=str(meses or ""),
            hint_text="Meses",
            width=80,
            keyboard_type=ft.KeyboardType.NUMBER,
        )

        tf_d = ft.TextField(value=data_db_para_br(data), width=130)

        tf_o = ft.TextField(value=obs or "", width=220)

        def sync():
            if tf_m.value.isdigit():
                d = _data_por_meses(data_base, int(tf_m.value))
                tf_d.value = data_db_para_br(_format_db(d))

        tf_m.on_change = lambda e: (sync(), page.update())

        def escolher(e):
            calendario_ptbr(
                page,
                on_select=lambda d: (
                    setattr(tf_d, "value", d.strftime("%d/%m/%Y")),
                    setattr(tf_m, "value", str(_calcular_meses(data_base, d))),
                    page.update(),
                ),
            )

        def remover(e):
            container_prazos.controls.remove(row)
            if existente and pid:
                excluir_prazos.add(pid)
            page.update()

        row = ft.Row(
            [
                tf_m,
                tf_d,
                ft.OutlinedButton("Calendário", on_click=escolher),
                tf_o,
                ft.TextButton("X", on_click=remover),
            ],
            spacing=6,
        )

        linhas_prazos.append((pid, tf_m, tf_d, tf_o))
        container_prazos.controls.append(row)

    for p in prazos:
        criar_linha_prazo(
            p["id"], p.get("meses"), p.get("data_vencimento"), p.get("observacao"), True
        )

    def novo_prazo(e):
        criar_linha_prazo(None)
        page.update()

    # -------------------------
    # PARTES
    # -------------------------

    partes_bd = get_partes()
    tipos_bd = get_tipos_partes()
    cp_existentes = get_contrato_partes(contrato["id"])

    secao_partes = _build_secao_partes(page, partes_bd, tipos_bd, cp_existentes)

    # -------------------------
    # SALVAR
    # -------------------------

    def salvar(e):

        if tf_vig.value and not tf_vig.value.isdigit():
            _snack(page, "Vigência inválida.")
            return

        try:
            # Contrato
            update_contrato(
                contrato["id"],
                {
                    "valor": tf_valor.value,
                    "responsavel": next((u["usuario"] for u in _usuarios if str(u["id"]) == (dd_resp.value or "")), dd_resp.value or ""),
                    "data_assinatura": data_br_para_db(tf_data_ass.value) if tf_data_ass.value else None,
                    "vigencia": int(tf_vig.value) if tf_vig.value else None,
                    "termo_final": data_br_para_db(tf_fim.value),
                },
            )

            # Prazos
            for pid in excluir_prazos:
                update_prazo(pid, {"ativo": False})

            for pid, tf_m, tf_d, tf_o in linhas_prazos:
                if pid in excluir_prazos:
                    continue
                if not tf_m.value and not tf_d.value and not tf_o.value:
                    continue
                meses = int(tf_m.value) if tf_m.value.isdigit() else None
                data_db = data_br_para_db(tf_d.value)
                payload = {
                    "meses": meses,
                    "data_vencimento": data_db,
                    "observacao": tf_o.value or "",
                }
                if pid:
                    update_prazo(pid, payload)
                else:
                    add_prazo(
                        contrato_id=contrato["id"],
                        meses=meses,
                        observacao=tf_o.value,
                        data_criacao=contrato["data_inicial"],
                        data_vencimento=data_db,
                    )

            # Partes — remove as excluídas
            for cp_id in secao_partes["excluir"]:
                delete_contrato_parte(cp_id)

            # Partes — adiciona as novas (cp_id == None)
            for linha in secao_partes["linhas"]:
                cp_id = linha["cp_id"]
                p_val = linha["dd_parte"].value
                t_val = linha["dd_tipo"].value
                if cp_id in secao_partes["excluir"]:
                    continue
                if not p_val or not t_val:
                    continue
                if cp_id is None:
                    add_contrato_parte(contrato["id"], int(p_val), t_val)

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
            height=640,
            content=ft.Column(
                [
                    tf_cliente,
                    tf_nome,
                    tf_valor,
                    dd_resp,

                    ft.Row([
                        ft.OutlinedButton("Calendário assinatura", on_click=escolher_data_ass),
                        tf_data_ass,
                    ]),

                    ft.Row([tf_data_ini]),
                    ft.Row([tf_vig, tf_fim]),

                    ft.Divider(),

                    # PRAZOS
                    ft.Row(
                        [
                            ft.Text("Prazos", weight=ft.FontWeight.BOLD),
                            ft.FilledButton("Adicionar", on_click=novo_prazo),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    container_prazos,

                    ft.Divider(),

                    # PARTES
                    secao_partes["widget"],
                ],
                spacing=10,
                scroll=ft.ScrollMode.AUTO,
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

    print(f"✅ ver_contrato_dialog chamado - contrato_id: {contrato.get('id')}")

    # Mesmas chamadas do editar_contrato_dialog
    prazos       = get_prazos_por_contrato(contrato["id"]) or []
    cp_existentes = get_contrato_partes(contrato["id"]) or []
    todas_partes  = get_partes() or []

    print(f"📋 prazos: {prazos}")
    print(f"👥 cp_existentes: {cp_existentes}")
    print(f"👤 todas_partes: {todas_partes}")

    partes_map   = {str(p["id"]): p for p in todas_partes}
    nome_cliente = clientes_map.get(contrato.get("cliente_id"), "-")

    # ---- PRAZOS ----
    if prazos:
        itens_prazos = [
            ft.Container(
                padding=ft.padding.symmetric(vertical=4, horizontal=8),
                border_radius=8,
                bgcolor=ft.Colors.GREY_50,
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

    # ---- PARTES ----
    if cp_existentes:
        itens_partes = [
            ft.Container(
                padding=ft.padding.symmetric(vertical=4, horizontal=8),
                border_radius=8,
                bgcolor=ft.Colors.GREY_50,
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
            for cp in cp_existentes
        ]
    else:
        itens_partes = [ft.Text("Nenhuma parte vinculada.", color=ft.Colors.GREY_500, italic=True, size=13)]

    # ---- DIALOG ----
    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text(contrato.get("nome", ""), weight=ft.FontWeight.BOLD),
        content=ft.Container(
            height=500,
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
                ],
                spacing=8,
                scroll=ft.ScrollMode.AUTO,
            ),
        ),
        actions=[
            ft.TextButton("Fechar", on_click=lambda e: _fechar_ver(dialog, page)),
        ],
    )

    page.overlay.append(dialog)
    dialog.open = True
    page.update()


def _fechar_ver(dialog, page):
    dialog.open = False
    page.update()