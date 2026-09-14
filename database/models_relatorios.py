# database/models_relatorios.py
#
# Queries para os relatórios usando Supabase Python SDK
# (mesmo padrão do database/models.py existente).
#
# SEGURANÇA: todas as funções filtram por tenant_id — isolamento total entre tenants.

from database.supabase_client import supabase


def _safe(query, msg="Erro Supabase"):
    try:
        return query.execute()
    except Exception as e:
        print(f"❌ {msg}: {e}")
        return None


# ──────────────────────────────────────────────
# DROPDOWN — lista de clientes
# ──────────────────────────────────────────────

def get_lista_clientes(tenant_id: str) -> list[dict]:
    """Retorna id + nome de todos os clientes do tenant para o dropdown de filtro."""
    resp = _safe(
        supabase.table("clientes")
        .select("id, nome")
        .eq("tenant_id", tenant_id)
        .order("nome"),
        "Erro lista clientes"
    )
    return resp.data if resp and resp.data else []


# ──────────────────────────────────────────────
# 1. CLIENTES
# ──────────────────────────────────────────────

def get_relatorio_clientes(
    tenant_id: str,
    cliente_id: int | None = None,
) -> list[dict]:
    """
    Todos os clientes do tenant.
    Campos: id, nome, tipo, documento, sigla
    """
    q = (
        supabase.table("clientes")
        .select("id, nome, tipo, documento, sigla")
        .eq("tenant_id", tenant_id)
        .order("nome")
    )
    if cliente_id:
        q = q.eq("id", cliente_id)

    resp = _safe(q, "Erro relatório clientes")
    return resp.data if resp and resp.data else []


# ──────────────────────────────────────────────
# 2. NOTIFICAÇÕES / ALERTAS
# ──────────────────────────────────────────────

def get_relatorio_notificacoes(
    tenant_id: str,
    status: str = "todos",
    cliente_id: int | None = None,
) -> list[dict]:
    """
    Alertas enviados da tabela notificacoes_enviadas.
    Faz JOIN via prazos → contratos → clientes, tudo filtrado por tenant_id.

    Campos retornados: cliente, contrato, observacao, data_vencimento, dias_antes, data_enviada
    """
    try:
        # FIX: a consulta anterior partia de "notificacoes_enviadas" com
        # INNER JOIN para "prazos" — isso restringe o universo da consulta
        # a prazos que JÁ têm notificação enviada. Um prazo sem nenhum
        # envio nunca gera linha em "notificacoes_enviadas", então ele
        # nunca aparecia no resultado, não importa o filtro de status
        # abaixo — os "Pendentes" estavam estruturalmente excluídos antes
        # mesmo de qualquer filtro rodar.
        #
        # Agora a consulta parte de "prazos" (o universo completo do
        # tenant) e traz "notificacoes_enviadas" como relação opcional
        # (embedded resource do PostgREST — equivalente a um LEFT JOIN):
        # se não houver notificação, a lista vem vazia e o prazo aparece
        # como "Pendente". Mesmo padrão já usado corretamente no Painel
        # de Alertas (get_alertas_por_periodo, em database/models.py).
        q = (
            supabase.table("prazos")
            .select(
                "id, observacao, data_vencimento, tenant_id,"
                "contratos!inner(id, nome, indice, data_inicial, deleted_at, tenant_id,"
                "  clientes!inner(id, nome, tenant_id)"
                "),"
                "notificacoes_enviadas(dias_antes, data_enviada)"
            )
            .eq("tenant_id", tenant_id)
        )

        resp = _safe(q, "Erro relatório notificações")
        if not resp or not resp.data:
            return []

        resultado = []
        for row in resp.data:
            contrato = row.get("contratos") or {}
            cliente  = contrato.get("clientes") or {}

            # Filtro deleted_at
            if contrato.get("deleted_at"):
                continue

            # Filtro cliente específico
            if cliente_id and cliente.get("id") != cliente_id:
                continue

            # notificacoes_enviadas vem como LISTA (relação 1-para-N);
            # vazia = nenhum envio registrado para este prazo = Pendente.
            notificacoes = row.get("notificacoes_enviadas") or []
            tem_envio = len(notificacoes) > 0
            ultima_notif = notificacoes[0] if notificacoes else {}

            # Filtro status
            if status == "enviados" and not tem_envio:
                continue
            if status == "pendentes" and tem_envio:
                continue

            resultado.append({
                "id":              contrato.get("id", ""),
                "indice":          contrato.get("indice", ""),
                "cliente":         cliente.get("nome", ""),
                "contrato":        contrato.get("nome", ""),
                "observacao":      row.get("observacao", ""),
                "inicio":          contrato.get("data_inicial", ""),
                "vencimento":      row.get("data_vencimento", ""),
                "dias_antes":      ultima_notif.get("dias_antes", "") if tem_envio else "-",
                "data_enviada":    ultima_notif.get("data_enviada", "") if tem_envio else "",
                "status":          "Enviado" if tem_envio else "Pendente",
            })

        # Ordena por cliente → vencimento
        resultado.sort(key=lambda d: (d["cliente"], str(d["vencimento"] or "")))
        return resultado

    except Exception as e:
        print(f"❌ Erro relatório notificações: {e}")
        return []


# ──────────────────────────────────────────────
# 3. CONTRATOS
# ──────────────────────────────────────────────

def get_relatorio_contratos(
    tenant_id: str,
    cliente_id: int | None = None,
) -> list[dict]:
    try:
        q = (
            supabase.table("contratos")
            .select(
                "id, nome, indice, data_inicial, data_assinatura, termo_final,"
                "tipo_contrato, valor, ativo,"
                "clientes!inner(id, nome)"
            )
            .eq("tenant_id", tenant_id)
            .is_("deleted_at", "null")
            .order("nome")
        )

        resp = _safe(q, "Erro relatório contratos")
        if not resp or not resp.data:
            return []

        resultado = []
        for row in resp.data:
            cli = row.get("clientes") or {}

            if cliente_id and cli.get("id") != cliente_id:
                continue

            resultado.append({
                "id":             row.get("id", ""),
                "cliente":        cli.get("nome", ""),
                "nome":           row.get("nome", ""),
                "indice":         row.get("indice", ""),
                "data_inicial":   row.get("data_inicial", ""),
                "data_assinatura":row.get("data_assinatura", ""),
                "termo_final":    row.get("termo_final", ""),
                "tipo_contrato":  row.get("tipo_contrato", ""),
                "valor":          row.get("valor", ""),
                "situacao":       "Ativo" if row.get("ativo") else "Inativo",
            })

        resultado.sort(key=lambda d: (d["cliente"], str(d["data_inicial"] or "")))
        return resultado

    except Exception as e:
        print(f"❌ Erro relatório contratos: {e}")
        return []
# ──────────────────────────────────────────────
# 4. PRAZOS
# ──────────────────────────────────────────────

def get_relatorio_prazos(
    tenant_id: str,
    cliente_id: int | None = None,
    data_inicio: str | None = None,
    data_final: str | None = None,
    tipo_contrato: str | None = None,
    tipo_prazo: str | None = None,
) -> list[dict]:
    """
    Todos os prazos do tenant com nome do cliente e do contrato.
    Campos: id (Identificador), cliente, contrato, tipo, observacao, meses,
            data_criacao (Data Início), data_vencimento, tipo_contrato

    Filtros (todos opcionais):
      cliente_id     -> id do cliente
      data_inicio/data_final -> intervalo de data_vencimento (inclusive)
      tipo_contrato  -> valor exato de contratos.tipo_contrato
      tipo_prazo     -> valor exato de prazos.tipo (ex: "Vencimento")

    FIX: a versão anterior buscava "data_base"/"base_tipo" (colunas que
    não existem no schema atual) e um join "tipos_prazos(nome)" via
    chave estrangeira que também não existe — "tipo" é uma coluna de
    texto direta em "prazos". Isso fazia a consulta inteira falhar e
    o relatório vir sempre vazio.
    """
    try:
        q = (
            supabase.table("prazos")
            .select(
                "id, tipo, observacao, meses, data_criacao, data_vencimento,"
                "contratos!inner(id, nome, indice, deleted_at, tipo_contrato,"
                "  clientes!inner(id, nome)"
                ")"
            )
            .eq("tenant_id", tenant_id)
        )

        if data_inicio:
            q = q.gte("data_vencimento", data_inicio)
        if data_final:
            q = q.lte("data_vencimento", data_final)
        if tipo_prazo:
            q = q.eq("tipo", tipo_prazo)

        q = q.order("data_vencimento")

        resp = _safe(q, "Erro relatório prazos")
        if not resp or not resp.data:
            return []

        resultado = []
        for row in resp.data:
            contrato = row.get("contratos") or {}
            cliente  = contrato.get("clientes") or {}

            # Ignora prazos de contratos deletados
            if contrato.get("deleted_at"):
                continue

            if cliente_id and cliente.get("id") != cliente_id:
                continue

            if tipo_contrato and contrato.get("tipo_contrato") != tipo_contrato:
                continue

            resultado.append({
                "id":              row.get("id", ""),
                "cliente":         cliente.get("nome", ""),
                "contrato":        contrato.get("nome", ""),
                "indice":          contrato.get("indice", ""),
                "tipo":            row.get("tipo", ""),
                "tipo_contrato":   contrato.get("tipo_contrato", ""),
                "observacao":      row.get("observacao", ""),
                "meses":           row.get("meses", ""),
                "data_criacao":    row.get("data_criacao", ""),
                "data_vencimento": row.get("data_vencimento", ""),
            })

        resultado.sort(key=lambda d: (d["cliente"], str(d["data_vencimento"] or "")))
        return resultado

    except Exception as e:
        print(f"❌ Erro relatório prazos: {e}")
        return []