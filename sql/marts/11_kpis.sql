-- Cartões executivos do painel de Auditoria Cidadã e Compliance.
-- Grão: a operação inteira, uma linha. Cada CTE resumo_* também tem uma linha só (1 x 1 x 1 x 1 = 1).
WITH resumo_geral AS (
    -- Grão: a operação inteira (lançamentos válidos).
    SELECT
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
    -- Grão: a operação inteira cruzada com o CEIS.
    SELECT
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
),
gasto_teto_deputado AS (
    -- Grão: um deputado federal (mesma regra de marts.ranking_deputados).
    -- meses_exercicio: meses entre a primeira e a última competência com despesa, inclusive.
    SELECT
        deputado_id,
        max(uf)                                         AS uf,
        sum(valor_liquido)                              AS despesa_liquida,
        max(mes_competencia) - min(mes_competencia) + 1 AS meses_exercicio
    FROM refined.despesas_ceap
    WHERE valor_liquido > 0
      AND deputado_id IS NOT NULL
    GROUP BY deputado_id
),
resumo_teto AS (
    -- Grão: a operação inteira (deputados com UF e, portanto, com teto).
    SELECT
        round(
            100.0 * sum(g.despesa_liquida) / sum(u.limite_mensal_cota * g.meses_exercicio),
            2
        ) AS pct_teto_utilizado_geral,
        count(*) AS deputados_com_teto,
        count(*) FILTER (
            WHERE round(100.0 * g.despesa_liquida / (u.limite_mensal_cota * g.meses_exercicio), 2) >= 90
        ) AS deputados_acima_90_teto
    FROM gasto_teto_deputado AS g
    JOIN refined.cotas_uf    AS u ON u.uf = g.uf
)
SELECT
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
FROM resumo_geral AS g, resumo_ceis AS c, resumo_recorrencia AS r, resumo_teto AS t
