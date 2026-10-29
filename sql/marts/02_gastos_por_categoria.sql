-- Quais categorias de despesa mais consomem recursos da Cota Parlamentar?
-- Grão: uma categoria de despesa em um ano (ano, categoria_despesa).
-- A soma de despesa_liquida de cada ano bate centavo por centavo com o mart 01.
SELECT
    ano_competencia                             AS ano,
    categoria_despesa,
    count(*)                                    AS lancamentos,
    count(DISTINCT documento_fornecedor)        AS fornecedores,
    sum(valor_documento)                        AS valor_bruto,
    sum(valor_glosa)                            AS valor_glosado,
    sum(valor_liquido)                          AS despesa_liquida,
    round(avg(valor_liquido), 2)                AS ticket_medio_nota,
    round(
        100.0 * sum(valor_liquido) / sum(sum(valor_liquido)) OVER (PARTITION BY ano_competencia),
        2
    ) AS pct_total
FROM refined.despesas_ceap
WHERE valor_liquido > 0
GROUP BY ano_competencia, categoria_despesa
ORDER BY ano, despesa_liquida DESC
