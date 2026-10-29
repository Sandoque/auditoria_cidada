-- Quantos parlamentares atuaram e quanto gastaram por UF?
-- Grão: uma Unidade da Federação (uf).
SELECT
    u.uf,
    u.nome_estado,
    u.regiao,
    count(DISTINCT d.deputado_id)          AS deputados,
    count(DISTINCT d.documento_fornecedor) AS fornecedores,
    sum(d.valor_liquido)                   AS despesa_liquida
FROM refined.cotas_uf      AS u
JOIN refined.despesas_ceap AS d ON d.uf = u.uf
WHERE d.valor_liquido > 0
  AND d.deputado_id IS NOT NULL
GROUP BY u.uf, u.nome_estado, u.regiao
ORDER BY despesa_liquida DESC
