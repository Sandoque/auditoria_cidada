-- Quanto foi pago a fornecedores limpos vs. sancionados no CEIS?
-- Grão: a operação inteira, uma linha.
-- Reduz sancoes_ceis a uma linha por documento antes do JOIN para não multiplicar notas.
WITH ceis_por_fornecedor AS (
    -- Grão: um documento_sancionado (CNPJ/CPF) presente no CEIS.
    SELECT
        documento_sancionado,
        min(data_inicio_sancao)                         AS data_inicio_min,
        max(coalesce(data_fim_sancao, DATE '2099-12-31')) AS data_fim_max
    FROM refined.sancoes_ceis
    GROUP BY documento_sancionado
),
avaliacao_notas AS (
    -- Grão: um lançamento válido da CEAP.
    SELECT
        d.valor_liquido,
        CASE
            WHEN c.documento_sancionado IS NULL THEN 'limpo'
            WHEN coalesce(d.data_emissao::DATE, make_date(d.ano_competencia, d.mes_competencia, 1))
                 BETWEEN c.data_inicio_min AND c.data_fim_max THEN 'sancao_vigente'
            ELSE 'sancao_historica'
        END AS situacao_ceis
    FROM refined.despesas_ceap AS d
    LEFT JOIN ceis_por_fornecedor AS c
           ON c.documento_sancionado = d.documento_fornecedor
    WHERE d.valor_liquido > 0
)
SELECT
    count(*) AS total_lancamentos,
    sum(CASE WHEN situacao_ceis = 'limpo' THEN 1 ELSE 0 END) AS lancamentos_limpos,
    sum(CASE WHEN situacao_ceis IN ('sancao_historica', 'sancao_vigente') THEN 1 ELSE 0 END) AS lancamentos_ceis,
    sum(CASE WHEN situacao_ceis = 'sancao_vigente' THEN 1 ELSE 0 END) AS lancamentos_sancao_vigente,
    sum(valor_liquido) AS despesa_total,
    sum(CASE WHEN situacao_ceis IN ('sancao_historica', 'sancao_vigente') THEN valor_liquido ELSE 0 END) AS despesa_fornecedores_ceis,
    sum(CASE WHEN situacao_ceis = 'sancao_vigente' THEN valor_liquido ELSE 0 END) AS despesa_sancao_vigente,
    round(
        100.0 * sum(CASE WHEN situacao_ceis = 'limpo' THEN valor_liquido ELSE 0 END)
        / sum(valor_liquido),
        2
    ) AS pct_valor_regular
FROM avaliacao_notas
