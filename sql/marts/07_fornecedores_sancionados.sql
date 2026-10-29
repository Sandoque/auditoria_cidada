-- Quais fornecedores inscritos no CEIS receberam pagamentos da Cota Parlamentar, e com que alcance de sanção?
-- Grão: um fornecedor sancionado no CEIS que recebeu recursos da CEAP em um ano (ano, documento_fornecedor).
-- Consolida sancoes_ceis por documento antes do JOIN para evitar multiplicação 1:N.
WITH resumo_ceis AS (
    -- Grão: um documento_sancionado no CEIS.
    SELECT
        documento_sancionado,
        count(*)                                          AS qtd_sancoes_ceis,
        min(nome_sancionado)                              AS nome_cadastro_ceis,
        min(categoria_sancao)                             AS categoria_sancao_principal,
        min(orgao_sancionador)                            AS orgao_sancionador_principal
    FROM refined.sancoes_ceis
    GROUP BY documento_sancionado
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
pagamentos_ceis AS (
    -- Grão: um lançamento válido da CEAP pago a fornecedor listado no CEIS.
    -- A subconsulta escalar devolve no máximo um valor por nota (NULL quando nenhuma sanção está vigente).
    SELECT
        d.ano_competencia AS ano,
        d.documento_fornecedor,
        d.nome_fornecedor,
        d.deputado_id,
        d.valor_liquido,
        c.qtd_sancoes_ceis,
        c.categoria_sancao_principal,
        c.orgao_sancionador_principal,
        (
            SELECT max(s.nivel_alcance)
            FROM alcance_por_sancao AS s
            WHERE s.documento_sancionado = d.documento_fornecedor
              AND coalesce(d.data_emissao::DATE, make_date(d.ano_competencia, d.mes_competencia, 1))
                  BETWEEN s.data_inicio_sancao AND s.data_fim_sancao
        ) AS nivel_alcance_vigente
    FROM refined.despesas_ceap AS d
    JOIN resumo_ceis           AS c ON c.documento_sancionado = d.documento_fornecedor
    WHERE d.valor_liquido > 0
)
SELECT
    ano,
    documento_fornecedor,
    max(nome_fornecedor)                                         AS nome_fornecedor,
    max(qtd_sancoes_ceis)                                        AS qtd_sancoes_ceis,
    max(categoria_sancao_principal)                              AS categoria_sancao,
    max(orgao_sancionador_principal)                             AS orgao_sancionador,
    count(*)                                                     AS lancamentos,
    count(DISTINCT deputado_id)                                  AS deputados_compradores,
    count(nivel_alcance_vigente)                                 AS lancamentos_em_vigencia,
    sum(valor_liquido)                                           AS valor_recebido_total,
    sum(CASE WHEN nivel_alcance_vigente IS NOT NULL THEN valor_liquido ELSE 0 END) AS valor_recebido_em_vigencia,
    CASE max(nivel_alcance_vigente)
        WHEN 3 THEN 'federal'
        WHEN 2 THEN 'sem_informacao'
        WHEN 1 THEN 'restrita'
    END                                                          AS alcance_sancao_vigente
FROM pagamentos_ceis
GROUP BY ano, documento_fornecedor
ORDER BY ano, valor_recebido_total DESC, documento_fornecedor
