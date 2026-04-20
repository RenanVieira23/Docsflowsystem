from datetime import datetime


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
