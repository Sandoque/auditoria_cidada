"""Verificação automatizada de Qualidade de Dados (Data Quality) sobre o banco gravado.

Aplica as sete famílias de regras de qualidade de dados (Aula 4, seção 09):
1. Não vazio: todo mart possui pelo menos 1 linha.
2. Chave única: chaves primárias não se repetem nas tabelas de refined e marts.
3. Sem nulo onde não pode: colunas obrigatórias sempre preenchidas.
4. Dentro do domínio: percentuais entre 0 e 100, meses entre 1 e 12, UFs válidas.
5. As partes somam o todo: em marts.conformidade_ceis, limpos + ceis = total_lancamentos.
6. Dois caminhos concordam: a receita/despesa de gastos_mensais, gastos_por_categoria,
   fornecedores_pareto, gastos_por_partido e kpis batem centavo por centavo, ano a ano
   (junção por `ano`, exigindo o mesmo conjunto de anos dos dois lados).
7. Nada some sem aviso: as linhas de refined batem com raw.
"""

import sys

from pipeline import db


def executar_qualidade() -> list[tuple[str, bool, str]]:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    con = db.conectar()
    regras: list[tuple[str, str]] = [
        (
            "Nada some sem aviso (raw.despesas_ceap == refined.despesas_ceap)",
            "SELECT (SELECT count(*) FROM raw.despesas_ceap) = (SELECT count(*) FROM refined.despesas_ceap)",
        ),
        (
            "Chave única em refined.deputados (deputado_id)",
            "SELECT count(*) = count(DISTINCT deputado_id) FROM refined.deputados",
        ),
        (
            "Chave única em refined.sancoes_ceis (sancao_id)",
            "SELECT count(*) = count(DISTINCT sancao_id) FROM refined.sancoes_ceis",
        ),
        (
            "Chave única em marts.gasto_medio_por_uf (27 UFs distintas em cada ano)",
            """
            SELECT bool_and(linhas = 27 AND ufs = 27)
            FROM (SELECT ano, count(*) AS linhas, count(DISTINCT uf) AS ufs FROM marts.gasto_medio_por_uf GROUP BY ano)
            """,
        ),
        (
            "Sem nulo onde não pode (documento_fornecedor e valor_liquido em refined.despesas_ceap)",
            "SELECT count(*) FILTER (WHERE documento_fornecedor IS NULL OR valor_liquido IS NULL) = 0 FROM refined.despesas_ceap",
        ),
        (
            "Dentro do domínio (pct_valor_regular entre 0 e 100 e mes_competencia entre 1 e 12)",
            """
            SELECT (SELECT bool_and(pct_valor_regular BETWEEN 0 AND 100) FROM marts.conformidade_ceis)
               AND (SELECT count(*) FILTER (WHERE mes_competencia NOT BETWEEN 1 AND 12) = 0 FROM refined.despesas_ceap)
            """,
        ),
        (
            "Dentro do domínio (todo deputado-ano com teto > 0 e nenhum dia de exercício sem limite cadastrado)",
            "SELECT bool_and(teto_periodo > 0 AND dias_sem_limite = 0) FROM marts.teto_deputado_ano",
        ),
        (
            "Nada some sem aviso (pelo menos 95% dos deputados de cada ano com período oficial de mandato)",
            """
            SELECT bool_and(oficiais >= 0.95 * total)
            FROM (
                SELECT ano, count(*) AS total, count(*) FILTER (WHERE fonte_periodo = 'oficial') AS oficiais
                FROM marts.teto_deputado_ano GROUP BY ano
            )
            """,
        ),
        (
            "As partes somam o todo (lancamentos_limpos + lancamentos_ceis == total_lancamentos no mart 03, por ano)",
            "SELECT bool_and(lancamentos_limpos + lancamentos_ceis = total_lancamentos) FROM marts.conformidade_ceis",
        ),
        (
            "As partes somam o todo (alcance federal + sem informação + restrita == sanção vigente no mart 03, por ano)",
            """
            SELECT bool_and(
                despesa_sancao_vigente_federal + despesa_sancao_vigente_sem_info + despesa_sancao_vigente_restrita
                    = despesa_sancao_vigente
                AND lancamentos_sancao_vigente_federal + lancamentos_sancao_vigente_sem_info + lancamentos_sancao_vigente_restrita
                    = lancamentos_sancao_vigente
            )
            FROM marts.conformidade_ceis
            """,
        ),
        (
            "Dois caminhos concordam (despesa_liquida idêntica nos marts 01, 02, 03, 09, 10 e 11, ano a ano)",
            """
            WITH m01 AS (SELECT ano, sum(despesa_liquida) AS v FROM marts.gastos_mensais GROUP BY ano),
                 m02 AS (SELECT ano, sum(despesa_liquida) AS v FROM marts.gastos_por_categoria GROUP BY ano),
                 m03 AS (SELECT ano, despesa_total AS v FROM marts.conformidade_ceis),
                 m09 AS (SELECT ano, sum(despesa_liquida) AS v FROM marts.fornecedores_pareto GROUP BY ano),
                 m10 AS (SELECT ano, sum(despesa_liquida) AS v FROM marts.gastos_por_partido GROUP BY ano),
                 m11 AS (SELECT ano, despesa_total_reais AS v FROM marts.kpis)
            SELECT count(*) = (SELECT count(*) FROM m01)
               AND count(*) = (SELECT count(*) FROM m11)
               AND bool_and(m01.v = m02.v AND m01.v = m03.v AND m01.v = m09.v AND m01.v = m10.v AND m01.v = m11.v)
            FROM m01
            JOIN m02 ON m02.ano = m01.ano
            JOIN m03 ON m03.ano = m01.ano
            JOIN m09 ON m09.ano = m01.ano
            JOIN m10 ON m10.ano = m01.ano
            JOIN m11 ON m11.ano = m01.ano
            """,
        ),
        (
            "As partes somam o todo (divulgação + demais categorias == despesa do mês, marts 13 e 01)",
            """
            SELECT count(*) = (SELECT count(*) FROM marts.gastos_mensais)
               AND bool_and(d.despesa_divulgacao + d.despesa_demais = m.despesa_liquida)
            FROM marts.divulgacao_eleitoral AS d
            JOIN marts.gastos_mensais AS m ON m.mes = d.mes
            """,
        ),
        (
            "Dois caminhos concordam em fornecedores sancionados (mart 03 vs soma do mart 07, ano a ano)",
            """
            WITH m07 AS (
                SELECT ano, sum(valor_recebido_total) AS total, sum(valor_recebido_em_vigencia) AS vigente
                FROM marts.fornecedores_sancionados GROUP BY ano
            )
            SELECT bool_and(
                c.despesa_fornecedores_ceis = coalesce(m07.total, 0)
                AND c.despesa_sancao_vigente = coalesce(m07.vigente, 0)
            )
            FROM marts.conformidade_ceis AS c
            LEFT JOIN m07 ON m07.ano = c.ano
            """,
        ),
        (
            "Dois caminhos concordam no alcance da sanção vigente (mart 03 vs mart 11, ano a ano)",
            """
            SELECT count(*) = (SELECT count(*) FROM marts.kpis)
               AND bool_and(
                c.despesa_sancao_vigente_federal = k.despesa_sancao_vigente_federal
                AND c.despesa_sancao_vigente_sem_info = k.despesa_sancao_vigente_sem_info
                AND c.despesa_sancao_vigente_restrita = k.despesa_sancao_vigente_restrita
            )
            FROM marts.conformidade_ceis AS c
            JOIN marts.kpis AS k ON k.ano = c.ano
            """,
        ),
        (
            "Dois caminhos concordam no uso do teto (marts 00, 04, 06 e 11, ano a ano)",
            """
            WITH m00 AS (SELECT ano, sum(despesa_liquida) AS despesa FROM marts.teto_deputado_ano GROUP BY ano),
                 m04 AS (
                     SELECT ano, sum(despesa_liquida) AS despesa,
                            round(100.0 * sum(despesa_liquida) / sum(teto_periodo), 2) AS pct
                     FROM marts.ranking_deputados GROUP BY ano
                 ),
                 m06 AS (SELECT ano, sum(despesa_total_uf) AS despesa FROM marts.gasto_medio_por_uf GROUP BY ano)
            SELECT count(*) = (SELECT count(*) FROM m00)
               AND bool_and(m04.despesa = m00.despesa AND m06.despesa = m00.despesa AND m04.pct = k.pct_teto_utilizado_geral)
            FROM m00
            JOIN m04 ON m04.ano = m00.ano
            JOIN m06 ON m06.ano = m00.ano
            JOIN marts.kpis AS k ON k.ano = m00.ano
            """,
        ),
    ]

    resultados: list[tuple[str, bool, str]] = []
    falhas = 0
    try:
        for descricao, sql in regras:
            ok = bool(con.execute(sql).fetchall()[0][0])
            simbolo = "✓" if ok else "✗"
            print(f"{simbolo} {descricao}")
            resultados.append((descricao, ok, sql))
            if not ok:
                falhas += 1
    finally:
        con.close()

    if falhas > 0:
        print(f"Erro: {falhas} regra(s) de qualidade de dados falharam.", file=sys.stderr)
        sys.exit(1)

    print(f"  {len(resultados)} regras de qualidade verificadas com sucesso.")
    return resultados


if __name__ == "__main__":
    executar_qualidade()
