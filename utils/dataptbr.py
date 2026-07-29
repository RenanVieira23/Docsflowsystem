from datetime import datetime
from dateutil.relativedelta import relativedelta


def data_db_para_br(data):
    if not data:
        return ""

    try:
        return datetime.strptime(data, "%Y-%m-%d").strftime("%d/%m/%Y")
    except:
        return data


def data_br_para_db(data):
    if not data:
        return None

    try:
        return datetime.strptime(data, "%d/%m/%Y").strftime("%Y-%m-%d")
    except:
        return None


def somar_meses(data_iso: str, meses) -> str | None:
    """
    Soma 'meses' a uma data no formato ISO (YYYY-MM-DD)  Usado no cálculo automático do prazo:
    Data = Data Início + Meses.
    """
    if not data_iso or meses in (None, ""):
        return None
    try:
        base = datetime.strptime(data_iso, "%Y-%m-%d")
        return (base + relativedelta(months=int(meses))).strftime("%Y-%m-%d")
    except Exception:
        return None