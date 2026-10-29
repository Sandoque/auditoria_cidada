-- Como os gastos se distribuem por partido político e Lideranças Partidárias?
-- Grão: uma sigla partidária (ou 'LIDERANCAS' quando partido é NULL).
SELECT
    coalesce(partido, 'LIDERANCAS')              AS partido,
    count(DISTINCT deputado_id)                  AS deputados_ativos,
    count(*)                                     AS lancamentos,
    sum(valor_liquido)                           AS despesa_liquida,
    round(avg(valor_liquido), 2)                 AS ticket_medio_nota,
    round(median(valor_liquido), 2)              AS ticket_mediana_nota,
    round(
        100.0 * sum(valor_liquido) / sum(sum(valor_liquido)) OVER (),
        2
    ) AS pct_total
FROM refined.despesas_ceap
WHERE valor_liquido > 0
GROUP BY 1
ORDER BY despesa_liquida DESC
