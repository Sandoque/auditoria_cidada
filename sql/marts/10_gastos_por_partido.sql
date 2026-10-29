-- Como os gastos se distribuem por partido político e Lideranças Partidárias, e quanto do teto cada partido usou?
-- Grão: uma sigla partidária (ou 'LIDERANCAS' quando partido é NULL).
WITH gasto_partido AS (
    -- Grão: uma sigla partidária (ou 'LIDERANCAS').
    SELECT
        coalesce(partido, 'LIDERANCAS')              AS partido,
        count(DISTINCT deputado_id)                  AS deputados_ativos,
        count(*)                                     AS lancamentos,
        sum(valor_liquido)                           AS despesa_liquida,
        round(avg(valor_liquido), 2)                 AS ticket_medio_nota,
        round(median(valor_liquido), 2)              AS ticket_mediana_nota
    FROM refined.despesas_ceap
    WHERE valor_liquido > 0
    GROUP BY 1
),
gasto_deputado_partido AS (
    -- Grão: um par (deputado_id, partido); quem trocou de partido divide o ano entre as siglas.
    -- meses_exercicio: meses entre a primeira e a última competência com despesa na sigla, inclusive.
    SELECT
        deputado_id,
        partido,
        uf,
        sum(valor_liquido) AS despesa_liquida,
        max(mes_competencia) - min(mes_competencia) + 1 AS meses_exercicio
    FROM refined.despesas_ceap
    WHERE valor_liquido > 0
      AND deputado_id IS NOT NULL
      AND partido IS NOT NULL
    GROUP BY deputado_id, partido, uf
),
uso_teto_partido AS (
    -- Grão: uma sigla partidária (Lideranças não têm teto individual e ficam de fora).
    SELECT
        g.partido,
        round(
            100.0 * sum(g.despesa_liquida) / sum(u.limite_mensal_cota * g.meses_exercicio),
            2
        ) AS pct_teto_utilizado
    FROM gasto_deputado_partido AS g
    JOIN refined.cotas_uf       AS u ON u.uf = g.uf
    GROUP BY g.partido
)
SELECT
    p.partido,
    p.deputados_ativos,
    p.lancamentos,
    p.despesa_liquida,
    p.ticket_medio_nota,
    p.ticket_mediana_nota,
    round(
        100.0 * p.despesa_liquida / sum(p.despesa_liquida) OVER (),
        2
    ) AS pct_total,
    t.pct_teto_utilizado
FROM gasto_partido         AS p
LEFT JOIN uso_teto_partido AS t ON t.partido = p.partido
ORDER BY p.despesa_liquida DESC
