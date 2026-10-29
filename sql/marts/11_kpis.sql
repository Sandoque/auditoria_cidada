-- Cartões executivos do painel de Auditoria Cidadã e Compliance.
-- Grão: um ano (ano), uma linha por ano. Cada CTE resumo_* também tem uma linha por ano.
WITH resumo_geral AS (
    -- Grão: um ano (lançamentos válidos).
    SELECT
        ano_competencia                                           AS ano,
        round(sum(valor_liquido) / 1000000.0, 2)                  AS despesa_total_milhoes,
        sum(valor_liquido)                                        AS despesa_total_reais,
        round(avg(valor_liquido), 2)                              AS ticket_medio_nota,
        round(median(valor_liquido), 2)                           AS ticket_mediana_nota,
        round(100.0 * sum(valor_glosa) / sum(valor_documento), 2) AS pct_glosado,
        sum(valor_glosa)                                          AS valor_glosado_total,
        count(DISTINCT deputado_id)                               AS deputados_ativos,
        count(DISTINCT documento_fornecedor)                      AS fornecedores_distintos
    FROM refined.despesas_ceap
    WHERE valor_liquido > 0
    GROUP BY ano_competencia
),
ceis_por_fornecedor AS (
    -- Grão: um documento_sancionado (CNPJ/CPF) no CEIS.
    SELECT DISTINCT documento_sancionado
    FROM refined.sancoes_ceis
),
alcance_por_sancao AS (
    -- Grão: uma sanção do CEIS, com o alcance lido de abrangencia_sancao e esfera_orgao_sancionador.
    -- nivel_alcance: 3 = federal, 2 = sem informação, 1 = restrita (vale o mais amplo).
    SELECT
        documento_sancionado,
        data_inicio_sancao,
        coalesce(data_fim_sancao, DATE '2099-12-31') AS data_fim_sancao,
        CASE
            WHEN abrangencia_sancao = 'Todas as Esferas em todos os Poderes' THEN 3
            WHEN abrangencia_sancao = 'Em todos os Poderes da Esfera do órgão sancionador'
             AND esfera_orgao_sancionador = 'FEDERAL' THEN 3
            WHEN abrangencia_sancao IN ('No órgão sancionador', 'Em outro órgão') THEN 1
            WHEN abrangencia_sancao IN (
                     'Em todos os Poderes da Esfera do órgão sancionador',
                     'Na Esfera e no Poder do órgão sancionador'
                 )
             AND esfera_orgao_sancionador IN ('ESTADUAL', 'MUNICIPAL') THEN 1
            ELSE 2
        END AS nivel_alcance
    FROM refined.sancoes_ceis
),
avaliacao_notas AS (
    -- Grão: um lançamento válido da CEAP.
    -- A subconsulta escalar devolve no máximo um valor por nota (NULL quando nenhuma sanção está vigente).
    SELECT
        d.ano_competencia AS ano,
        d.documento_fornecedor,
        d.valor_liquido,
        c.documento_sancionado IS NOT NULL AS no_ceis,
        (
            SELECT max(s.nivel_alcance)
            FROM alcance_por_sancao AS s
            WHERE s.documento_sancionado = d.documento_fornecedor
              AND coalesce(d.data_emissao::DATE, make_date(d.ano_competencia, d.mes_competencia, 1))
                  BETWEEN s.data_inicio_sancao AND s.data_fim_sancao
        ) AS nivel_alcance_vigente
    FROM refined.despesas_ceap AS d
    LEFT JOIN ceis_por_fornecedor AS c
           ON c.documento_sancionado = d.documento_fornecedor
    WHERE d.valor_liquido > 0
),
resumo_ceis AS (
    -- Grão: um ano cruzado com o CEIS.
    SELECT
        ano,
        sum(CASE WHEN no_ceis THEN valor_liquido ELSE 0 END) AS despesa_fornecedores_ceis,
        sum(CASE WHEN nivel_alcance_vigente IS NOT NULL THEN valor_liquido ELSE 0 END) AS despesa_sancao_vigente,
        count(nivel_alcance_vigente) AS lancamentos_sancao_vigente,
        sum(CASE WHEN nivel_alcance_vigente = 3 THEN valor_liquido ELSE 0 END) AS despesa_sancao_vigente_federal,
        sum(CASE WHEN nivel_alcance_vigente = 2 THEN valor_liquido ELSE 0 END) AS despesa_sancao_vigente_sem_info,
        sum(CASE WHEN nivel_alcance_vigente = 1 THEN valor_liquido ELSE 0 END) AS despesa_sancao_vigente_restrita,
        count(*) FILTER (WHERE nivel_alcance_vigente = 3) AS lancamentos_sancao_vigente_federal,
        count(DISTINCT documento_fornecedor) FILTER (WHERE nivel_alcance_vigente = 3) AS fornecedores_sancao_vigente_federal,
        round(
            100.0 * sum(CASE WHEN NOT no_ceis THEN valor_liquido ELSE 0 END)
            / sum(valor_liquido),
            2
        ) AS pct_valor_regular
    FROM avaliacao_notas
    GROUP BY ano
),
pagamentos_fornecedor AS (
    -- Grão: um fornecedor com lançamento válido em um ano.
    SELECT
        ano_competencia AS ano,
        documento_fornecedor,
        count(*) AS qtd_pagamentos
    FROM refined.despesas_ceap
    WHERE valor_liquido > 0
    GROUP BY ano_competencia, documento_fornecedor
),
resumo_recorrencia AS (
    -- Grão: um ano (percentual de fornecedores com 2 ou mais pagamentos).
    SELECT
        ano,
        round(
            100.0 * count(*) FILTER (WHERE qtd_pagamentos > 1) / count(*),
            2
        ) AS pct_fornecedores_recorrentes
    FROM pagamentos_fornecedor
    GROUP BY ano
),
resumo_teto AS (
    -- Grão: um ano. Teto por dia de efetivo exercício, de marts.teto_deputado_ano.
    SELECT
        ano,
        round(100.0 * sum(despesa_liquida) / sum(teto_periodo), 2) AS pct_teto_utilizado_geral,
        count(*)                                                   AS deputados_com_teto,
        count(*) FILTER (WHERE pct_teto_utilizado >= 90)           AS deputados_acima_90_teto
    FROM marts.teto_deputado_ano
    GROUP BY ano
)
SELECT
    g.ano,
    g.despesa_total_milhoes,
    g.despesa_total_reais,
    g.ticket_medio_nota,
    g.ticket_mediana_nota,
    g.pct_glosado,
    g.valor_glosado_total,
    g.deputados_ativos,
    g.fornecedores_distintos,
    c.despesa_fornecedores_ceis,
    c.despesa_sancao_vigente,
    c.lancamentos_sancao_vigente,
    c.despesa_sancao_vigente_federal,
    c.despesa_sancao_vigente_sem_info,
    c.despesa_sancao_vigente_restrita,
    c.lancamentos_sancao_vigente_federal,
    c.fornecedores_sancao_vigente_federal,
    c.pct_valor_regular,
    r.pct_fornecedores_recorrentes,
    t.pct_teto_utilizado_geral,
    t.deputados_com_teto,
    t.deputados_acima_90_teto
FROM resumo_geral            AS g
JOIN resumo_ceis             AS c ON c.ano = g.ano
JOIN resumo_recorrencia      AS r ON r.ano = g.ano
LEFT JOIN resumo_teto        AS t ON t.ano = g.ano
ORDER BY g.ano
