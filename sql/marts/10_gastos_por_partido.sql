-- Como os gastos se distribuem por partido político e Lideranças Partidárias, e quanto do teto cada partido usou?
-- Grão: uma sigla partidária (ou 'LIDERANCAS' quando partido é NULL) em um ano (ano, partido).
WITH gasto_partido AS (
    -- Grão: (ano, partido), pelo partido de cada lançamento.
    SELECT
        ano_competencia                              AS ano,
        coalesce(partido, 'LIDERANCAS')              AS partido,
        count(DISTINCT deputado_id)                  AS deputados_ativos,
        count(*)                                     AS lancamentos,
        sum(valor_liquido)                           AS despesa_liquida,
        round(avg(valor_liquido), 2)                 AS ticket_medio_nota,
        round(median(valor_liquido), 2)              AS ticket_mediana_nota
    FROM refined.despesas_ceap
    WHERE valor_liquido > 0
    GROUP BY 1, 2
),
uso_teto_partido AS (
    -- Grão: (ano, partido), pelo partido mais recente do deputado no ano (marts.teto_deputado_ano).
    -- Lideranças não têm teto individual e ficam de fora.
    SELECT
        ano,
        partido,
        round(100.0 * sum(despesa_liquida) / sum(teto_periodo), 2) AS pct_teto_utilizado
    FROM marts.teto_deputado_ano
    GROUP BY ano, partido
)
SELECT
    p.ano,
    p.partido,
    p.deputados_ativos,
    p.lancamentos,
    p.despesa_liquida,
    p.ticket_medio_nota,
    p.ticket_mediana_nota,
    round(
        100.0 * p.despesa_liquida / sum(p.despesa_liquida) OVER (PARTITION BY p.ano),
        2
    ) AS pct_total,
    t.pct_teto_utilizado
FROM gasto_partido         AS p
LEFT JOIN uso_teto_partido AS t ON t.ano = p.ano AND t.partido = p.partido
ORDER BY p.ano, p.despesa_liquida DESC
