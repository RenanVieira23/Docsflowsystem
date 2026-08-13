"""
utils/erros_ui.py
==================
Camada central de mensagens de erro amigáveis para o usuário final.

Por que existe: expor `str(exception)` direto na tela — o padrão
`_snack(page, f"Erro: {ex}")` usado em várias telas do sistema — vaza
detalhes internos do Postgres/Supabase (nomes de coluna, constraints,
stack trace) e não ajuda o usuário a entender o que fazer a respeito.
Este módulo traduz os erros mais comuns para mensagens claras em
português. O erro técnico completo continua sendo sempre logado no
console (e, quando a chamada passa por run_db, também no banco via
_log_erro_run_db) — só o texto exibido na tela muda.

Uso típico (ação pontual — salvar, excluir, etc.):

    from utils.erros_ui import snack_erro

    try:
        await run_db(page, add_cliente, dados)
    except Exception as ex:
        snack_erro(page, ex, contexto="salvar o cliente")
        return

Uso típico (carregamento de tela que falhou):

    from utils.erros_ui import banner_erro_carregamento

    try:
        dados = await run_db(page, get_clientes, tenant_id)
    except Exception as ex:
        print("Erro clientes:", ex)
        dados = []
        self._erro_carregamento = True
    ...
    if self._erro_carregamento:
        self.controls.append(banner_erro_carregamento("os clientes", on_retry=self.recarregar))
"""

import flet as ft


# Padrões de texto (em inglês, como o Postgres/Supabase retornam) que
# mapeiam para uma mensagem amigável em português. Comparação é
# case-insensitive e por substring — não precisa bater exatamente.
_PADROES_CONHECIDOS = [
    ("duplicate key", "Já existe um registro com esses dados."),
    ("unique constraint", "Já existe um registro com esses dados."),
    ("violates row-level security", "Você não tem permissão para realizar esta ação."),
    ("row-level security policy", "Você não tem permissão para realizar esta ação."),
    ("jwt expired", "Sua sessão expirou. Faça login novamente."),
    ("invalid jwt", "Sua sessão expirou. Faça login novamente."),
    ("permission denied", "Você não tem permissão para realizar esta ação."),
    ("timeout", "O servidor demorou para responder. Tente novamente."),
    ("connection", "Falha de conexão com o servidor. Verifique sua internet e tente novamente."),
    ("network", "Falha de conexão com o servidor. Verifique sua internet e tente novamente."),
    ("foreign key", "Não é possível concluir: existem outros registros vinculados a este."),
    ("null value in column", "Preencha todos os campos obrigatórios."),
    ("value too long", "Um dos campos ultrapassa o tamanho máximo permitido."),
    ("invalid input syntax", "Um dos campos foi preenchido em um formato inválido."),
]


def mensagem_amigavel(ex: Exception, contexto: str = "concluir a operação") -> str:
    """
    Traduz uma exceção técnica para uma mensagem clara em português.
    Se nenhum padrão conhecido for reconhecido, cai numa mensagem
    genérica — nunca expõe o texto cru da exceção ao usuário.
    """
    texto = str(ex).lower()
    for padrao, mensagem in _PADROES_CONHECIDOS:
        if padrao in texto:
            return mensagem
    return f"Não foi possível {contexto}. Tente novamente em instantes."


def snack_erro(page: ft.Page, ex: Exception, contexto: str = "concluir a operação"):
    """
    Mostra um SnackBar com mensagem amigável derivada da exceção.
    Substitui o padrão antigo `_snack(page, f"Erro: {ex}")`.
    """
    msg = mensagem_amigavel(ex, contexto)
    print(f"⚠️ UI erro ({contexto}): {ex}")
    page.snack_bar = ft.SnackBar(ft.Text(msg), bgcolor=ft.Colors.RED_100)
    page.snack_bar.open = True
    page.update()


def snack_sucesso(page: ft.Page, mensagem: str):
    """Padroniza também o caminho de sucesso (cor verde), para
    diferenciar visualmente de um erro — hoje ambos usavam o mesmo
    SnackBar cinza padrão, sem distinção visual."""
    page.snack_bar = ft.SnackBar(ft.Text(mensagem), bgcolor=ft.Colors.GREEN_100)
    page.snack_bar.open = True
    page.update()


def banner_erro_carregamento(contexto: str = "os dados", on_retry=None) -> ft.Container:
    """
    Componente visual para quando o carregamento assíncrono de uma
    tela falha (ex: dentro de _carregar_dados). Diferente do
    snack_erro (aviso passageiro), este é um bloco fixo na tela —
    mais adequado quando a lista/tabela ficou vazia por causa do erro,
    não porque simplesmente não há dados cadastrados ainda.
    """
    controles = [
        ft.Icon(ft.Icons.CLOUD_OFF, size=28, color=ft.Colors.RED_300),
        ft.Text(
            f"Não foi possível carregar {contexto}.",
            size=13, color=ft.Colors.RED_700, weight=ft.FontWeight.W_600,
            text_align=ft.TextAlign.CENTER,
        ),
        ft.Text(
            "Verifique sua conexão e tente novamente.",
            size=12, color=ft.Colors.GREY_600,
            text_align=ft.TextAlign.CENTER,
        ),
    ]
    if on_retry:
        controles.append(
            ft.TextButton("Tentar novamente", icon=ft.Icons.REFRESH, on_click=on_retry)
        )

    return ft.Container(
        padding=16,
        border_radius=10,
        bgcolor=ft.Colors.RED_50,
        border=ft.border.all(1, ft.Colors.RED_100),
        content=ft.Column(
            controles,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=4,
        ),
    )