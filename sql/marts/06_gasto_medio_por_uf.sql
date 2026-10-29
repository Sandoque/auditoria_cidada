-- Qual o gasto anual médio por deputado em cada UF frente ao limite oficial da cota?
-- Grão: uma Unidade da Federação (uf).
-- O grão muda duas vezes: de lançamento para deputado, e de deputado para UF.
WITH gasto_por_deputado AS (
    -- Grão: um deputado federal com UF associada.
    SELECT
        deputado_id,
        uf,
        count(*)           AS lancamentos,
        sum(valor_liquido) AS despesa_anual_deputado
    FROM refined.despesas_ceap
    WHERE valor_liquido > 0
      AND deputado_id IS NOT NULL
      AND uf IS NOT NULL
    GROUP BY deputado_id, uf
)
SELECT
    g.uf,
    u.nome_estado,
    u.regiao,
    count(*)                                    AS deputados,
    sum(g.lancamentos)                          AS lancamentos,
    sum(g.despesa_anual_deputado)               AS despesa_total_uf,
    round(avg(g.despesa_anual_deputado), 2)     AS gasto_medio_deputado,
    round(median(g.despesa_anual_deputado), 2)  AS gasto_mediana_deputado,
    u.limite_mensal_cota
FROM gasto_por_deputado    AS g
JOIN refined.cotas_uf      AS u ON u.uf = g.uf
GROUP BY g.uf, u.nome_estado, u.regiao, u.limite_mensal_cota
ORDER BY gasto_medio_deputado DESC
