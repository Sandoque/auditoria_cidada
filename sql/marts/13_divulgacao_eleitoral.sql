-- A divulgação do mandato some da cota nos 120 dias antes da eleição, como manda o Ato da Mesa n. 43/2009?
-- Grão: um mês de competência (ano, mes), separando a divulgação das demais categorias.
-- Art. 2º, XII: a cota não paga divulgação nos 120 dias anteriores às eleições federais, estaduais ou
-- municipais, salvo se o Deputado não for candidato. Eleições: primeiro domingo de outubro dos anos
-- pares (Constituição, arts. 28, 29 e 77); anos ímpares ficam com data_eleicao NULL.
WITH gasto_mes AS (
    -- Grão: (ano, mes_competencia).
    SELECT
        ano_competencia                                                                     AS ano,
        mes_competencia,
        sum(valor_liquido) FILTER (WHERE categoria_despesa ILIKE 'DIVULGA%')                AS despesa_divulgacao,
        sum(valor_liquido) FILTER (WHERE categoria_despesa NOT ILIKE 'DIVULGA%')            AS despesa_demais,
        count(DISTINCT deputado_id) FILTER (WHERE categoria_despesa ILIKE 'DIVULGA%')       AS deputados_divulgacao
    FROM refined.despesas_ceap
    WHERE valor_liquido > 0
    GROUP BY ano_competencia, mes_competencia
),
eleicao AS (
    -- Grão: um ano. dayofweek: domingo = 0.
    SELECT DISTINCT
        ano,
        CASE
            WHEN ano % 2 = 0
            THEN make_date(ano, 10, 1) + CAST((7 - dayofweek(make_date(ano, 10, 1))) % 7 AS INTEGER)
        END AS data_eleicao
    FROM gasto_mes
)
SELECT
    g.ano,
    make_date(g.ano, g.mes_competencia, 1) AS mes,
    coalesce(g.despesa_divulgacao, 0)      AS despesa_divulgacao,
    coalesce(g.despesa_demais, 0)          AS despesa_demais,
    g.deputados_divulgacao,
    e.data_eleicao,
    e.data_eleicao - 120                   AS inicio_vedacao
FROM gasto_mes   AS g
JOIN eleicao     AS e ON e.ano = g.ano
ORDER BY mes
