-- Qual o gasto anual médio por deputado em cada UF e quanto do teto oficial da cota foi usado?
-- Grão: uma Unidade da Federação em um ano (ano, uf).
-- O grão muda duas vezes: de lançamento para deputado (marts.teto_deputado_ano), e de deputado para UF.
WITH lancamentos_deputado AS (
    -- Grão: (ano, deputado_id).
    SELECT ano_competencia AS ano, deputado_id, count(*) AS lancamentos
    FROM refined.despesas_ceap
    WHERE valor_liquido > 0
      AND deputado_id IS NOT NULL
    GROUP BY ano_competencia, deputado_id
)
SELECT
    t.ano,
    t.uf,
    u.nome_estado,
    u.regiao,
    count(*)                                    AS deputados,
    sum(l.lancamentos)                          AS lancamentos,
    sum(t.despesa_liquida)                      AS despesa_total_uf,
    round(avg(t.despesa_liquida), 2)            AS gasto_medio_deputado,
    round(median(t.despesa_liquida), 2)         AS gasto_mediana_deputado,
    max(t.limite_mensal_vigente)                AS limite_mensal_cota,
    sum(t.meses_exercicio)                      AS deputado_meses,
    round(100.0 * sum(t.despesa_liquida) / sum(t.teto_periodo), 2) AS pct_teto_utilizado
FROM marts.teto_deputado_ano AS t
JOIN lancamentos_deputado    AS l ON l.ano = t.ano AND l.deputado_id = t.deputado_id
JOIN refined.cotas_uf        AS u ON u.uf = t.uf
GROUP BY t.ano, t.uf, u.nome_estado, u.regiao
ORDER BY t.ano, pct_teto_utilizado DESC
