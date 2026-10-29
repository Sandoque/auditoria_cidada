-- Quanto a Cota Parlamentar desembolsou por mês de competência?
-- Grão: um mês de competência (ano, mes).
-- Só lançamentos válidos (valor_liquido > 0).
SELECT
    ano_competencia                                AS ano,
    make_date(ano_competencia, mes_competencia, 1) AS mes,
    count(*)                                       AS lancamentos,
    count(DISTINCT deputado_id)                    AS deputados_ativos,
    sum(valor_liquido)                             AS despesa_liquida,
    sum(valor_glosa)                               AS valor_glosado
FROM refined.despesas_ceap
WHERE valor_liquido > 0
GROUP BY ano_competencia, mes_competencia
ORDER BY mes
