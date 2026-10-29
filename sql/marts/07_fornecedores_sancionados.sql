-- Quais fornecedores inscritos no CEIS receberam pagamentos da Cota Parlamentar?
-- Grão: um fornecedor sancionado no CEIS que recebeu recursos da CEAP (documento_fornecedor).
-- Consolida sancoes_ceis por documento antes do JOIN para evitar multiplicação 1:N.
WITH resumo_ceis AS (
    -- Grão: um documento_sancionado no CEIS.
    SELECT
        documento_sancionado,
        count(*)                                          AS qtd_sancoes_ceis,
        min(nome_sancionado)                              AS nome_cadastro_ceis,
        min(categoria_sancao)                             AS categoria_sancao_principal,
        min(orgao_sancionador)                            AS orgao_sancionador_principal,
        min(data_inicio_sancao)                           AS primeira_sancao,
        max(coalesce(data_fim_sancao, DATE '2099-12-31')) AS ultima_sancao_fim
    FROM refined.sancoes_ceis
    GROUP BY documento_sancionado
),
pagamentos_ceis AS (
    -- Grão: um lançamento válido da CEAP pago a fornecedor listado no CEIS.
    SELECT
        d.documento_fornecedor,
        d.nome_fornecedor,
        d.deputado_id,
        d.valor_liquido,
        c.qtd_sancoes_ceis,
        c.categoria_sancao_principal,
        c.orgao_sancionador_principal,
        c.primeira_sancao,
        c.ultima_sancao_fim,
        CASE
            WHEN coalesce(d.data_emissao::DATE, make_date(d.ano_competencia, d.mes_competencia, 1))
                 BETWEEN c.primeira_sancao AND c.ultima_sancao_fim THEN 1
            ELSE 0
        END AS em_vigencia
    FROM refined.despesas_ceap AS d
    JOIN resumo_ceis           AS c ON c.documento_sancionado = d.documento_fornecedor
    WHERE d.valor_liquido > 0
)
SELECT
    documento_fornecedor,
    max(nome_fornecedor)                                         AS nome_fornecedor,
    max(qtd_sancoes_ceis)                                        AS qtd_sancoes_ceis,
    max(categoria_sancao_principal)                              AS categoria_sancao,
    max(orgao_sancionador_principal)                             AS orgao_sancionador,
    count(*)                                                     AS lancamentos,
    count(DISTINCT deputado_id)                                  AS deputados_compradores,
    sum(em_vigencia)                                             AS lancamentos_em_vigencia,
    sum(valor_liquido)                                           AS valor_recebido_total,
    sum(CASE WHEN em_vigencia = 1 THEN valor_liquido ELSE 0 END) AS valor_recebido_em_vigencia
FROM pagamentos_ceis
GROUP BY documento_fornecedor
ORDER BY valor_recebido_total DESC, documento_fornecedor
