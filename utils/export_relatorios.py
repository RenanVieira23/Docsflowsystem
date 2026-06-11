# utils/export_relatorios.py
#
# Exportação para Excel (.xlsx) e PDF via ReportLab.
# Cada relatório tem seu próprio par de funções: exportar_*_excel / exportar_*_pdf.

from __future__ import annotations

import io
from datetime import datetime
from typing import Any
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph

from utils.dataptbr import data_db_para_br


# ══════════════════════════════════════════════════════════════════════
# TEMA VISUAL
# ══════════════════════════════════════════════════════════════════════

_AZUL_ESCURO = colors.HexColor("#1565C0")
_AZUL_CLARO  = colors.HexColor("#E3F2FD")
_CINZA_BORDA = colors.HexColor("#BDBDBD")
_TEXTO       = colors.HexColor("#212121")


# ══════════════════════════════════════════════════════════════════════
# HELPERS INTERNOS
# ══════════════════════════════════════════════════════════════════════

def _buffer_excel(df: pd.DataFrame, sheet_name: str) -> io.BytesIO:
    """Gera BytesIO de um .xlsx com auto-largura de colunas."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
        ws = writer.sheets[sheet_name]
        for col_cells in ws.columns:
            max_len = max(
                (len(str(c.value)) if c.value is not None else 0)
                for c in col_cells
            )
            ws.column_dimensions[col_cells[0].column_letter].width = min(max_len + 4, 55)
    buf.seek(0)
    return buf


def _build_pdf(
    titulo: str,
    colunas: list[str],
    linhas: list[list[str]],
    orientacao: str = "retrato",        # "retrato" | "paisagem"
    col_widths: list[float] | None = None,   # larguras em cm (opcional)
) -> io.BytesIO:
    """Monta PDF estilizado com tabela e retorna BytesIO."""
    buf  = io.BytesIO()
    page = landscape(A4) if orientacao == "paisagem" else A4

    doc = SimpleDocTemplate(
        buf, pagesize=page,
        leftMargin=1.5*cm, rightMargin=1.5*cm,
        topMargin=1.5*cm,  bottomMargin=1.5*cm,
    )

    styles = getSampleStyleSheet()
    style_celula = ParagraphStyle(
    "CELULA",
    parent=styles["BodyText"],
    fontSize=7,
    leading=9,
    wordWrap="CJK",
)
    story: list[Any] = [
        Paragraph(titulo, ParagraphStyle(
            "H", parent=styles["Heading1"],
            fontSize=14, textColor=_AZUL_ESCURO, spaceAfter=4,
        )),
        Paragraph(
            f"Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')}",
            ParagraphStyle("S", parent=styles["Normal"],
                           fontSize=8, textColor=colors.grey, spaceAfter=10),
        ),
    ]

    avail_w = page[0] - 3*cm
    n_cols  = len(colunas)
    if col_widths:
        cw = [w * cm for w in col_widths]
    else:
        cw = [avail_w / n_cols] * n_cols

    table_data = [colunas]

    for linha in linhas:
        nova_linha = []

        for valor in linha:
            texto = str(valor).replace("\n", "<br/>")
            nova_linha.append(Paragraph(texto, style_celula))

        table_data.append(nova_linha)
    tbl = Table(table_data, colWidths=cw, repeatRows=1)
    tbl.setStyle(TableStyle([
        # cabeçalho
        ("BACKGROUND",    (0, 0), (-1, 0),  _AZUL_ESCURO),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
        ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0),  8),
        ("ALIGN",         (0, 0), (-1, 0),  "CENTER"),
        ("TOPPADDING",    (0, 0), (-1, 0),  6),
        ("BOTTOMPADDING", (0, 0), (-1, 0),  6),
        # dados
        ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",      (0, 1), (-1, -1), 7),
        ("TEXTCOLOR",     (0, 1), (-1, -1), _TEXTO),
        ("ALIGN",         (0, 1), (-1, -1), "LEFT"),
        ("TOPPADDING",    (0, 1), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
        ("GRID",          (0, 0), (-1, -1), 0.25, _CINZA_BORDA),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, _AZUL_CLARO]),
    ]))

    story.append(tbl)
    doc.build(story)
    buf.seek(0)
    return buf


def _fmt_datas(d: dict, chaves: list[str], campos_data: set[str]) -> list[str]:
    row = []
    for k in chaves:
        v = d.get(k, "") or ""
        if k in campos_data:
            v = data_db_para_br(v)
        row.append(str(v))
    return row


# ══════════════════════════════════════════════════════════════════════
# 1. CLIENTES
# ══════════════════════════════════════════════════════════════════════

_CHAVES_CLI = ["id", "nome", "tipo", "documento", "sigla"]
_COLS_CLI   = ["ID", "Nome", "Tipo", "Documento", "Sigla"]


def exportar_clientes_excel(dados: list[dict]) -> tuple[io.BytesIO, str]:
    df = pd.DataFrame(dados).reindex(columns=_CHAVES_CLI)
    df.columns = _COLS_CLI
    nome = f"relatorio_clientes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return _buffer_excel(df, "Clientes"), nome


def exportar_clientes_pdf(dados: list[dict]) -> tuple[io.BytesIO, str]:
    linhas = [_fmt_datas(d, _CHAVES_CLI, set()) for d in dados]
    buf  = _build_pdf("Relatório de Clientes", _COLS_CLI, linhas)
    nome = f"relatorio_clientes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return buf, nome


# ══════════════════════════════════════════════════════════════════════
# 2. ALERTAS / NOTIFICAÇÕES
# ══════════════════════════════════════════════════════════════════════

_CHAVES_ALT = ["cliente", "contrato", "observacao", "inicio", "vencimento", "dias_antes", "status"]
_COLS_ALT   = ["Cliente", "Contrato", "Observação", "Início", "Vencimento", "Dias antes", "Status"]
_DATAS_ALT  = {"inicio", "vencimento"}


def exportar_alertas_excel(dados: list[dict], status: str = "todos") -> tuple[io.BytesIO, str]:
    df = pd.DataFrame(dados).reindex(columns=_CHAVES_ALT)
    for col in _DATAS_ALT:
        if col in df.columns:
            df[col] = df[col].apply(data_db_para_br)
    df.columns = _COLS_ALT
    nome = f"relatorio_alertas_{status}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return _buffer_excel(df, "Alertas"), nome


def exportar_alertas_pdf(dados: list[dict], status: str = "todos") -> tuple[io.BytesIO, str]:
    linhas = [_fmt_datas(d, _CHAVES_ALT, _DATAS_ALT) for d in dados]
    buf  = _build_pdf("Relatório de Alertas", _COLS_ALT, linhas, "paisagem")
    nome = f"relatorio_alertas_{status}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return buf, nome


# ══════════════════════════════════════════════════════════════════════
# 3. CONTRATOS  — schema real (nome, indice, data_inicial,
#                               data_assinatura, termo_final)
# ══════════════════════════════════════════════════════════════════════

_CHAVES_CON = [
    "cliente", "nome", "indice",
    "data_inicial", "data_assinatura", "termo_final",
    "tipo_contrato", "valor", "situacao",
]
_COLS_CON = [
    "Cliente", "Nome do Contrato", "Identificador",
    "Data Inicial", "Data Assinatura", "Termo Final",
    "Tipo", "Valor", "Situação",
]
_DATAS_CON = {"data_inicial", "data_assinatura"}
# termo_final é text no schema (pode conter texto ou data) → não converte


def exportar_contratos_excel(dados: list[dict]) -> tuple[io.BytesIO, str]:
    df = pd.DataFrame(dados).reindex(columns=_CHAVES_CON)
    for col in _DATAS_CON:
        if col in df.columns:
            df[col] = df[col].apply(data_db_para_br)
    df.columns = _COLS_CON
    nome = f"relatorio_contratos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return _buffer_excel(df, "Contratos"), nome


def exportar_contratos_pdf(dados: list[dict]) -> tuple[io.BytesIO, str]:
    linhas = [_fmt_datas(d, _CHAVES_CON, _DATAS_CON) for d in dados]
    # larguras proporcionais: cliente e nome mais largos
    col_w = [3.5, 4.0, 2.0, 2.2, 2.2, 2.5, 2.2, 2.0, 1.8]
    buf  = _build_pdf("Relatório de Contratos", _COLS_CON, linhas,
                      "paisagem", col_widths=col_w)
    nome = f"relatorio_contratos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return buf, nome


# ══════════════════════════════════════════════════════════════════════
# 4. PRAZOS
# ══════════════════════════════════════════════════════════════════════

_CHAVES_PRA = [
    "cliente", "contrato", "tipo_prazo", "observacao",
    "meses", "data_base", "base_tipo", "data_criacao", "data_vencimento",
]
_COLS_PRA = [
    "Cliente", "Contrato", "Tipo de Prazo", "Observação",
    "Meses", "Data Base", "Tipo Base", "Criação", "Vencimento",
]
_DATAS_PRA = {"data_base", "data_criacao", "data_vencimento"}


def exportar_prazos_excel(dados: list[dict]) -> tuple[io.BytesIO, str]:
    df = pd.DataFrame(dados).reindex(columns=_CHAVES_PRA)
    for col in _DATAS_PRA:
        if col in df.columns:
            df[col] = df[col].apply(data_db_para_br)
    df.columns = _COLS_PRA
    nome = f"relatorio_prazos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return _buffer_excel(df, "Prazos"), nome


def exportar_prazos_pdf(dados: list[dict]) -> tuple[io.BytesIO, str]:
    linhas = [_fmt_datas(d, _CHAVES_PRA, _DATAS_PRA) for d in dados]
    buf  = _build_pdf("Relatório de Prazos", _COLS_PRA, linhas, "paisagem")
    nome = f"relatorio_prazos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return buf, nome