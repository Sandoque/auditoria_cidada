-- Quais categorias de despesa mais consomem recursos da Cota Parlamentar?
-- Grão: uma categoria de despesa (categoria_despesa).
-- A soma de despesa_liquida bate centavo por centavo com o mart 01.
SELECT
    categoria_despesa,
    count(*)                                    AS lancamentos,
    count(DISTINCT documento_fornecedor)        AS fornecedores,
    sum(valor_documento)                        AS valor_bruto,
    sum(valor_glosa)                            AS valor_glosado,
    sum(valor_liquido)                          AS despesa_liquida,
    round(avg(valor_liquido), 2)                AS ticket_medio_nota
FROM refined.despesas_ceap
WHERE valor_liquido > 0
GROUP BY categoria_despesa
ORDER BY despesa_liquida DESC
