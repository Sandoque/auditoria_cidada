-- Em quais categorias de despesa a auditoria da Câmara mais aplica glosas (cortes)?
-- Grão: uma categoria de despesa em um ano (ano, categoria_despesa).
SELECT
    ano_competencia                                                AS ano,
    categoria_despesa,
    count(*)                                                       AS lancamentos,
    count(*) FILTER (WHERE valor_glosa > 0)                        AS lancamentos_glosados,
    round(100.0 * count(*) FILTER (WHERE valor_glosa > 0) / count(*), 2) AS pct_notas_glosadas,
    sum(valor_documento)                                           AS valor_bruto,
    sum(valor_glosa)                                               AS valor_glosado,
    round(100.0 * sum(valor_glosa) / sum(valor_documento), 2)      AS pct_valor_glosado
FROM refined.despesas_ceap
WHERE valor_liquido > 0
GROUP BY ano_competencia, categoria_despesa
ORDER BY ano, valor_glosado DESC
