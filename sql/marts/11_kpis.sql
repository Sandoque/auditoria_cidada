-- Cartões executivos do painel de Auditoria Cidadã e Compliance.
-- Grão: a operação inteira, uma linha. Cada CTE também tem uma linha só (1 x 1 x 1 = 1).
WITH resumo_geral AS (
    -- Grão: a operação inteira (lançamentos válidos).
    SELECT
        round(sum(valor_liquido) / 1000000.0, 2)                  AS despesa_total_milhoes,
        sum(valor_liquido)                                        AS despesa_total_reais,
        round(avg(valor_liquido), 2)                              AS ticket_medio_nota,
        round(median(valor_liquido), 2)                           AS ticket_mediana_nota,
        round(100.0 * sum(valor_glosa) / sum(valor_documento), 2) AS pct_glosado,
        count(DISTINCT deputado_id)                               AS deputados_ativos,
        count(DISTINCT documento_fornecedor)                      AS fornecedores_distintos
    FROM refined.despesas_ceap
    WHERE valor_liquido > 0
),
ceis_por_fornecedor AS (
    -- Grão: um documento_sancionado (CNPJ/CPF) no CEIS.
    SELECT
        documento_sancionado,
        min(data_inicio_sancao)                           AS data_inicio_min,
        max(coalesce(data_fim_sancao, DATE '2099-12-31')) AS data_fim_max
    FROM refined.sancoes_ceis
    GROUP BY documento_sancionado
),
resumo_ceis AS (
    -- Grão: a operação inteira cruzada com o CEIS.
    SELECT
        sum(CASE WHEN c.documento_sancionado IS NOT NULL THEN d.valor_liquido ELSE 0 END) AS despesa_fornecedores_ceis,
        sum(
            CASE
                WHEN c.documento_sancionado IS NOT NULL
                 AND coalesce(d.data_emissao::DATE, make_date(d.ano_competencia, d.mes_competencia, 1))
                     BETWEEN c.data_inicio_min AND c.data_fim_max
                THEN d.valor_liquido
                ELSE 0
            END
        ) AS despesa_sancao_vigente,
        sum(
            CASE
                WHEN c.documento_sancionado IS NOT NULL
                 AND coalesce(d.data_emissao::DATE, make_date(d.ano_competencia, d.mes_competencia, 1))
                     BETWEEN c.data_inicio_min AND c.data_fim_max
                THEN 1
                ELSE 0
            END
        ) AS lancamentos_sancao_vigente,
        round(
            100.0 * sum(CASE WHEN c.documento_sancionado IS NULL THEN d.valor_liquido ELSE 0 END)
            / sum(d.valor_liquido),
            2
        ) AS pct_valor_regular
    FROM refined.despesas_ceap AS d
    LEFT JOIN ceis_por_fornecedor AS c
           ON c.documento_sancionado = d.documento_fornecedor
    WHERE d.valor_liquido > 0
),
pagamentos_fornecedor AS (
    -- Grão: um fornecedor com lançamento válido.
    SELECT
        documento_fornecedor,
        count(*) AS qtd_pagamentos
    FROM refined.despesas_ceap
    WHERE valor_liquido > 0
    GROUP BY documento_fornecedor
),
resumo_recorrencia AS (
    -- Grão: a operação inteira (percentual de fornecedores com 2 ou mais pagamentos).
    SELECT
        round(
            100.0 * count(*) FILTER (WHERE qtd_pagamentos > 1) / count(*),
            2
        ) AS pct_fornecedores_recorrentes
    FROM pagamentos_fornecedor
)
SELECT
    g.despesa_total_milhoes,
    g.despesa_total_reais,
    g.ticket_medio_nota,
    g.ticket_mediana_nota,
    g.pct_glosado,
    g.deputados_ativos,
    g.fornecedores_distintos,
    c.despesa_fornecedores_ceis,
    c.despesa_sancao_vigente,
    c.lancamentos_sancao_vigente,
    c.pct_valor_regular,
    r.pct_fornecedores_recorrentes
FROM resumo_geral AS g, resumo_ceis AS c, resumo_recorrencia AS r
