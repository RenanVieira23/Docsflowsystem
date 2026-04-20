import unidecode

def gerar_sigla(nome: str) -> str:
    """
    Gera uma sigla automática:
    Primeira letra da primeira palavra + primeira letra da segunda (se existir).
    Sempre maiúscula e sem acentos.
    """
    if not nome:
        return ""

    nome_limpo = unidecode.unidecode(nome.strip().upper())
    partes = nome_limpo.split()

    if len(partes) == 0:
        return ""
    elif len(partes) == 1:
        return partes[0][0]  # só a primeira letra
    else:
        return partes[0][0] + partes[1][0]
