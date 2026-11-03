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

import logging
import sys
from collections.abc import Callable
from typing import NamedTuple

import duckdb

from pipeline import db

logger = logging.getLogger(__name__)


class RegraQualidade(NamedTuple):
    descricao: str
    sql: str


def regra_despesas_raw_igual_refined() -> RegraQualidade:
    """Família 7 · Nada some sem aviso entre raw.despesas_ceap e refined.despesas_ceap."""
    return RegraQualidade(
        "Nada some sem aviso (raw.despesas_ceap == refined.despesas_ceap)",
        "SELECT (SELECT count(*) FROM raw.despesas_ceap) = (SELECT count(*) FROM refined.despesas_ceap)",
    )


def regra_chave_unica_deputados() -> RegraQualidade:
    """Família 2 · Chave única em refined.deputados."""
    return RegraQualidade(
        "Chave única em refined.deputados (deputado_id)",
        "SELECT count(*) = count(DISTINCT deputado_id) FROM refined.deputados",
    )


def regra_chave_unica_sancoes_ceis() -> RegraQualidade:
    """Família 2 · Chave única em refined.sancoes_ceis."""
    return RegraQualidade(
        "Chave única em refined.sancoes_ceis (sancao_id)",
        "SELECT count(*) = count(DISTINCT sancao_id) FROM refined.sancoes_ceis",
    )


def regra_chave_unica_gasto_medio_uf() -> RegraQualidade:
    """Família 2 · 27 UFs distintas em cada ano em marts.gasto_medio_por_uf."""
    return RegraQualidade(
        "Chave única em marts.gasto_medio_por_uf (27 UFs distintas em cada ano)",
        """
        SELECT bool_and(linhas = 27 AND ufs = 27)
        FROM (SELECT ano, count(*) AS linhas, count(DISTINCT uf) AS ufs FROM marts.gasto_medio_por_uf GROUP BY ano)
        """,
    )


def regra_sem_nulos_despesas() -> RegraQualidade:
    """Família 3 · Sem nulo nas colunas obrigatórias de refined.despesas_ceap."""
    return RegraQualidade(
        "Sem nulo onde não pode (documento_fornecedor e valor_liquido em refined.despesas_ceap)",
        "SELECT count(*) FILTER (WHERE documento_fornecedor IS NULL OR valor_liquido IS NULL) = 0 FROM refined.despesas_ceap",
    )


def regra_dominio_percentual_e_mes() -> RegraQualidade:
    """Família 4 · Percentual regular entre 0 e 100 e mês de competência entre 1 e 12."""
    return RegraQualidade(
        "Dentro do domínio (pct_valor_regular entre 0 e 100 e mes_competencia entre 1 e 12)",
        """
        SELECT (SELECT bool_and(pct_valor_regular BETWEEN 0 AND 100) FROM marts.conformidade_ceis)
           AND (SELECT count(*) FILTER (WHERE mes_competencia NOT BETWEEN 1 AND 12) = 0 FROM refined.despesas_ceap)
        """,
    )


def regra_dominio_teto_deputado_ano() -> RegraQualidade:
    """Família 4 · Todo deputado-ano com teto positivo e nenhum dia sem limite cadastrado."""
    return RegraQualidade(
        "Dentro do domínio (todo deputado-ano com teto > 0 e nenhum dia de exercício sem limite cadastrado)",
        "SELECT bool_and(teto_periodo > 0 AND dias_sem_limite = 0) FROM marts.teto_deputado_ano",
    )


def regra_cobertura_periodo_oficial_mandato() -> RegraQualidade:
    """Família 7 · Pelo menos 95% dos deputados de cada ano com período oficial de mandato."""
    return RegraQualidade(
        "Nada some sem aviso (pelo menos 95% dos deputados de cada ano com período oficial de mandato)",
        """
        SELECT bool_and(oficiais >= 0.95 * total)
        FROM (
            SELECT ano, count(*) AS total, count(*) FILTER (WHERE fonte_periodo = 'oficial') AS oficiais
            FROM marts.teto_deputado_ano GROUP BY ano
        )
        """,
    )


def regra_partes_somam_todo_lancamentos_ceis() -> RegraQualidade:
    """Família 5 · Lançamentos limpos + CEIS somam o total de lançamentos no mart 03."""
    return RegraQualidade(
        "As partes somam o todo (lancamentos_limpos + lancamentos_ceis == total_lancamentos no mart 03, por ano)",
        "SELECT bool_and(lancamentos_limpos + lancamentos_ceis = total_lancamentos) FROM marts.conformidade_ceis",
    )


def regra_partes_somam_todo_alcance_sancao() -> RegraQualidade:
    """Família 5 · As três faixas de alcance somam o total em sanção vigente no mart 03."""
    return RegraQualidade(
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
    )


def regra_reconciliacao_despesa_liquida_marts() -> RegraQualidade:
    """Família 6 · Despesa líquida idêntica nos marts 01, 02, 03, 09, 10 e 11, ano a ano."""
    return RegraQualidade(
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
    )


def regra_partes_somam_todo_divulgacao_eleitoral() -> RegraQualidade:
    """Família 5 · Divulgação + demais categorias somam a despesa do mês (marts 13 e 01)."""
    return RegraQualidade(
        "As partes somam o todo (divulgação + demais categorias == despesa do mês, marts 13 e 01)",
        """
        SELECT count(*) = (SELECT count(*) FROM marts.gastos_mensais)
           AND bool_and(d.despesa_divulgacao + d.despesa_demais = m.despesa_liquida)
        FROM marts.divulgacao_eleitoral AS d
        JOIN marts.gastos_mensais AS m ON m.mes = d.mes
        """,
    )


def regra_reconciliacao_fornecedores_sancionados() -> RegraQualidade:
    """Família 6 · Totais de fornecedores sancionados batem entre o mart 03 e o mart 07."""
    return RegraQualidade(
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
    )


def regra_reconciliacao_alcance_sancao_kpis() -> RegraQualidade:
    """Família 6 · Valores por alcance da sanção vigente batem entre o mart 03 e o mart 11."""
    return RegraQualidade(
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
    )


def regra_reconciliacao_uso_do_teto() -> RegraQualidade:
    """Família 6 · Uso do teto e despesa dos deputados batem entre os marts 00, 04, 06 e 11."""
    return RegraQualidade(
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
    )


REGRAS_QUALIDADE: tuple[Callable[[], RegraQualidade], ...] = (
    regra_despesas_raw_igual_refined,
    regra_chave_unica_deputados,
    regra_chave_unica_sancoes_ceis,
    regra_chave_unica_gasto_medio_uf,
    regra_sem_nulos_despesas,
    regra_dominio_percentual_e_mes,
    regra_dominio_teto_deputado_ano,
    regra_cobertura_periodo_oficial_mandato,
    regra_partes_somam_todo_lancamentos_ceis,
    regra_partes_somam_todo_alcance_sancao,
    regra_reconciliacao_despesa_liquida_marts,
    regra_partes_somam_todo_divulgacao_eleitoral,
    regra_reconciliacao_fornecedores_sancionados,
    regra_reconciliacao_alcance_sancao_kpis,
    regra_reconciliacao_uso_do_teto,
)


def avaliar_regra(con: duckdb.DuckDBPyConnection, regra: RegraQualidade) -> tuple[str, bool, str]:
    """Executa uma regra SQL booleana no banco e registra o resultado no log."""
    ok = bool(con.execute(regra.sql).fetchall()[0][0])
    simbolo = "✓" if ok else "✗"
    logger.info("%s %s", simbolo, regra.descricao)
    return (regra.descricao, ok, regra.sql)


def executar_qualidade() -> list[tuple[str, bool, str]]:
    """Executa todas as funções de regra de qualidade e encerra com código 1 se alguma falhar."""
    db.configurar_logging()
    con = db.conectar()
    try:
        resultados = [avaliar_regra(con, fabrica()) for fabrica in REGRAS_QUALIDADE]
    finally:
        con.close()

    falhas = sum(1 for _, ok, _ in resultados if not ok)
    if falhas > 0:
        logger.error("Erro: %d regra(s) de qualidade de dados falharam.", falhas)
        sys.exit(1)

    logger.info("  %d regras de qualidade verificadas com sucesso.", len(resultados))
    return resultados


if __name__ == "__main__":
    executar_qualidade()
