-- Quantos fornecedores receberam um pagamento único vs. pagamentos recorrentes?
-- Grão: uma faixa de quantidade de recebimentos por fornecedor.
-- Fornecedor é o CNPJ/CPF normalizado (documento_fornecedor), nunca a razão social.
WITH pagamentos_por_fornecedor AS (
    -- Grão: um fornecedor (documento_fornecedor).
    SELECT
        documento_fornecedor,
        count(*)           AS qtd_pagamentos,
        sum(valor_liquido) AS despesa_liquida
    FROM refined.despesas_ceap
    WHERE valor_liquido > 0
    GROUP BY documento_fornecedor
),
faixas AS (
    -- Grão: um fornecedor classificado na sua faixa de recorrência.
    SELECT
        CASE
            WHEN qtd_pagamentos = 1 THEN 1
            WHEN qtd_pagamentos = 2 THEN 2
            WHEN qtd_pagamentos = 3 THEN 3
            WHEN qtd_pagamentos BETWEEN 4 AND 5 THEN 4
            WHEN qtd_pagamentos BETWEEN 6 AND 10 THEN 5
            WHEN qtd_pagamentos BETWEEN 11 AND 24 THEN 6
            ELSE 7
        END AS ordem_faixa,
        CASE
            WHEN qtd_pagamentos = 1 THEN '1 pagamento'
            WHEN qtd_pagamentos = 2 THEN '2 pagamentos'
            WHEN qtd_pagamentos = 3 THEN '3 pagamentos'
            WHEN qtd_pagamentos BETWEEN 4 AND 5 THEN '4 a 5 pagamentos'
            WHEN qtd_pagamentos BETWEEN 6 AND 10 THEN '6 a 10 pagamentos'
            WHEN qtd_pagamentos BETWEEN 11 AND 24 THEN '11 a 24 pagamentos'
            ELSE '25+ pagamentos'
        END AS faixa_pagamentos,
        despesa_liquida
    FROM pagamentos_por_fornecedor
)
SELECT
    ordem_faixa,
    faixa_pagamentos,
    count(*)                                                   AS fornecedores,
    round(100.0 * count(*) / sum(count(*)) OVER (), 2)         AS pct_fornecedores,
    sum(despesa_liquida)                                       AS despesa_liquida,
    round(100.0 * sum(despesa_liquida) / sum(sum(despesa_liquida)) OVER (), 2) AS pct_despesa
FROM faixas
GROUP BY ordem_faixa, faixa_pagamentos
ORDER BY ordem_faixa
