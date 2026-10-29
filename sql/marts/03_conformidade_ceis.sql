-- Quanto foi pago a fornecedores limpos vs. sancionados no CEIS, e com que alcance de sanção?
-- Grão: um ano (ano), uma linha por ano.
-- Reduz sancoes_ceis a uma linha por documento antes do JOIN para não multiplicar notas.
WITH ceis_por_fornecedor AS (
    -- Grão: um documento_sancionado (CNPJ/CPF) presente no CEIS.
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
    -- A subconsulta escalar devolve no máximo um valor por nota: o alcance mais amplo entre
    -- as sanções cuja janela contém a data da nota (NULL quando nenhuma está vigente).
    SELECT
        d.ano_competencia AS ano,
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
)
SELECT
    ano,
    count(*) AS total_lancamentos,
    count(*) FILTER (WHERE NOT no_ceis) AS lancamentos_limpos,
    count(*) FILTER (WHERE no_ceis) AS lancamentos_ceis,
    count(nivel_alcance_vigente) AS lancamentos_sancao_vigente,
    count(*) FILTER (WHERE nivel_alcance_vigente = 3) AS lancamentos_sancao_vigente_federal,
    count(*) FILTER (WHERE nivel_alcance_vigente = 2) AS lancamentos_sancao_vigente_sem_info,
    count(*) FILTER (WHERE nivel_alcance_vigente = 1) AS lancamentos_sancao_vigente_restrita,
    sum(valor_liquido) AS despesa_total,
    sum(CASE WHEN no_ceis THEN valor_liquido ELSE 0 END) AS despesa_fornecedores_ceis,
    sum(CASE WHEN nivel_alcance_vigente IS NOT NULL THEN valor_liquido ELSE 0 END) AS despesa_sancao_vigente,
    sum(CASE WHEN nivel_alcance_vigente = 3 THEN valor_liquido ELSE 0 END) AS despesa_sancao_vigente_federal,
    sum(CASE WHEN nivel_alcance_vigente = 2 THEN valor_liquido ELSE 0 END) AS despesa_sancao_vigente_sem_info,
    sum(CASE WHEN nivel_alcance_vigente = 1 THEN valor_liquido ELSE 0 END) AS despesa_sancao_vigente_restrita,
    round(
        100.0 * sum(CASE WHEN NOT no_ceis THEN valor_liquido ELSE 0 END)
        / sum(valor_liquido),
        2
    ) AS pct_valor_regular
FROM avaliacao_notas
GROUP BY ano
ORDER BY ano
