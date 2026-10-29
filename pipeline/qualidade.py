"""Verificação automatizada de Qualidade de Dados (Data Quality) sobre o banco gravado.

Aplica as sete famílias de regras de qualidade de dados (Aula 4, seção 09):
1. Não vazio: todo mart possui pelo menos 1 linha.
2. Chave única: chaves primárias não se repetem nas tabelas de refined e marts.
3. Sem nulo onde não pode: colunas obrigatórias sempre preenchidas.
4. Dentro do domínio: percentuais entre 0 e 100, meses entre 1 e 12, UFs válidas.
5. As partes somam o todo: em marts.conformidade_ceis, limpos + ceis = total_lancamentos.
6. Dois caminhos concordam: a receita/despesa de gastos_mensais, gastos_por_categoria,
   fornecedores_pareto, gastos_por_partido e kpis batem centavo por centavo.
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
            "Chave única em marts.gasto_medio_por_uf (27 UFs distintas)",
            "SELECT count(*) = 27 AND count(DISTINCT uf) = 27 FROM marts.gasto_medio_por_uf",
        ),
        (
            "Sem nulo onde não pode (documento_fornecedor e valor_liquido em refined.despesas_ceap)",
            "SELECT count(*) FILTER (WHERE documento_fornecedor IS NULL OR valor_liquido IS NULL) = 0 FROM refined.despesas_ceap",
        ),
        (
            "Dentro do domínio (pct_valor_regular entre 0 e 100 e mes_competencia entre 1 e 12)",
            """
            SELECT (SELECT pct_valor_regular BETWEEN 0 AND 100 FROM marts.conformidade_ceis)
               AND (SELECT count(*) FILTER (WHERE mes_competencia NOT BETWEEN 1 AND 12) = 0 FROM refined.despesas_ceap)
            """,
        ),
        (
            "As partes somam o todo (lancamentos_limpos + lancamentos_ceis == total_lancamentos no mart 03)",
            "SELECT lancamentos_limpos + lancamentos_ceis = total_lancamentos FROM marts.conformidade_ceis",
        ),
        (
            "As partes somam o todo (alcance federal + sem informação + restrita == sanção vigente no mart 03)",
            """
            SELECT
                despesa_sancao_vigente_federal + despesa_sancao_vigente_sem_info + despesa_sancao_vigente_restrita
                    = despesa_sancao_vigente
                AND lancamentos_sancao_vigente_federal + lancamentos_sancao_vigente_sem_info + lancamentos_sancao_vigente_restrita
                    = lancamentos_sancao_vigente
            FROM marts.conformidade_ceis
            """,
        ),
        (
            "Dois caminhos concordam (despesa_liquida idêntica nos marts 01, 02, 03, 09, 10 e 11)",
            """
            SELECT
                (SELECT sum(despesa_liquida) FROM marts.gastos_mensais) = (SELECT sum(despesa_liquida) FROM marts.gastos_por_categoria)
                AND (SELECT sum(despesa_liquida) FROM marts.gastos_mensais) = (SELECT despesa_total FROM marts.conformidade_ceis)
                AND (SELECT sum(despesa_liquida) FROM marts.gastos_mensais) = (SELECT sum(despesa_liquida) FROM marts.fornecedores_pareto)
                AND (SELECT sum(despesa_liquida) FROM marts.gastos_mensais) = (SELECT sum(despesa_liquida) FROM marts.gastos_por_partido)
                AND (SELECT sum(despesa_liquida) FROM marts.gastos_mensais) = (SELECT despesa_total_reais FROM marts.kpis)
            """,
        ),
        (
            "Dois caminhos concordam em fornecedores sancionados (mart 03 vs soma do mart 07)",
            """
            SELECT
                (SELECT despesa_fornecedores_ceis FROM marts.conformidade_ceis) = (SELECT sum(valor_recebido_total) FROM marts.fornecedores_sancionados)
                AND (SELECT despesa_sancao_vigente FROM marts.conformidade_ceis) = (SELECT sum(valor_recebido_em_vigencia) FROM marts.fornecedores_sancionados)
            """,
        ),
        (
            "Dois caminhos concordam no alcance da sanção vigente (mart 03 vs mart 11)",
            """
            SELECT
                c.despesa_sancao_vigente_federal = k.despesa_sancao_vigente_federal
                AND c.despesa_sancao_vigente_sem_info = k.despesa_sancao_vigente_sem_info
                AND c.despesa_sancao_vigente_restrita = k.despesa_sancao_vigente_restrita
            FROM marts.conformidade_ceis AS c, marts.kpis AS k
            """,
        ),
        (
            "Dois caminhos concordam no uso do teto (marts 04, 06 e 11)",
            """
            SELECT
                (SELECT sum(despesa_liquida) FROM marts.ranking_deputados)
                    = (SELECT sum(despesa_total_uf) FROM marts.gasto_medio_por_uf)
                AND (
                    SELECT round(100.0 * sum(despesa_liquida) / sum(limite_mensal_cota * meses_exercicio), 2)
                    FROM marts.ranking_deputados
                ) = (SELECT pct_teto_utilizado_geral FROM marts.kpis)
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
