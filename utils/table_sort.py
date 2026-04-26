"""
utils/table_sort.py
====================
Helper de ordenação para ft.DataTable.

Como usar em qualquer view:

    from utils.table_sort import SortState, col_sort

    # No __init__:
    self.sort = SortState()

    # Nas colunas da tabela:
    ft.DataColumn(ft.Text("Nome"), on_sort=self.sort.handler(1)),

    # Antes de renderizar as linhas:
    lista = self.sort.apply(lista, chaves=["id", "nome", "tipo", "documento", "sigla"])
    # (chaves: uma string por coluna, na mesma ordem)

    # No DataTable:
    self.tabela.sort_column_index = self.sort.col
    self.tabela.sort_ascending    = self.sort.asc
"""


class SortState:
    """Guarda coluna atual e direção, e ordena qualquer lista de dicts."""

    def __init__(self, default_col: int = 0, default_asc: bool = True):
        self.col = default_col
        self.asc = default_asc
        self._callback = None   # função chamada após mudar o estado

    def set_callback(self, fn):
        """Registra a função que re-renderiza a tabela."""
        self._callback = fn

    def handler(self, col_index: int):
        """Retorna o on_sort para um DataColumn específico."""
        def _on_sort(e):
            if self.col == col_index:
                self.asc = not self.asc
            else:
                self.col = col_index
                self.asc = True
            if self._callback:
                self._callback()
        return _on_sort

    def apply(self, data: list, chaves: list) -> list:
        """
        Ordena `data` pela coluna atual.

        chaves: lista de strings com o nome do campo em cada posição de coluna.
                Use None para colunas não ordenáveis (ex: "Ações").

        Exemplo:
            chaves = ["id", "nome", "tipo", "documento", "sigla", None]
        """
        if not data:
            return data

        if self.col >= len(chaves):
            return data

        chave = chaves[self.col]

        if chave is None:
            return data

        def _key(item):
            v = item.get(chave)
            if v is None:
                return (2, "")  # nulls por último; tipo compatível com (0,float) e (1,str)
            # Tenta ordenar como número se possível
            try:
                return (0, float(str(v)))
            except (ValueError, TypeError):
                return (1, str(v).lower())

        return sorted(data, key=_key, reverse=not self.asc)