-- Quais parlamentares mais utilizaram a Cota Parlamentar, quanto do teto usaram e quão concentrado foi o gasto?
-- Grão: um deputado federal com lançamento válido (deputado_id IS NOT NULL).
-- Exclui os 937 lançamentos institucionais de Lideranças Partidárias (onde deputado_id é NULL).
WITH gastos_deputado AS (
    -- Grão: um deputado_id.
    -- meses_exercicio: meses entre a primeira e a última competência com despesa, inclusive.
    SELECT
        d.deputado_id,
        max(d.nome_parlamentar)              AS nome_parlamentar,
        max(d.partido)                       AS partido,
        max(d.uf)                            AS uf,
        count(*)                             AS lancamentos,
        count(DISTINCT d.documento_fornecedor) AS fornecedores_distintos,
        sum(d.valor_liquido)                 AS despesa_liquida,
        round(avg(d.valor_liquido), 2)       AS ticket_medio_nota,
        max(d.mes_competencia) - min(d.mes_competencia) + 1 AS meses_exercicio
    FROM refined.despesas_ceap AS d
    WHERE d.valor_liquido > 0
      AND d.deputado_id IS NOT NULL
    GROUP BY d.deputado_id
),
gasto_deputado_fornecedor AS (
    -- Grão: um par (deputado_id, documento_fornecedor).
    SELECT
        deputado_id,
        documento_fornecedor,
        max(nome_fornecedor) AS nome_fornecedor,
        sum(valor_liquido)   AS despesa_fornecedor
    FROM refined.despesas_ceap
    WHERE valor_liquido > 0
      AND deputado_id IS NOT NULL
    GROUP BY deputado_id, documento_fornecedor
),
maior_fornecedor AS (
    -- Grão: um deputado_id (o fornecedor que mais recebeu dele; empate vai para o menor documento).
    SELECT deputado_id, nome_fornecedor, despesa_fornecedor
    FROM gasto_deputado_fornecedor
    QUALIFY row_number() OVER (
        PARTITION BY deputado_id ORDER BY despesa_fornecedor DESC, documento_fornecedor
    ) = 1
)
SELECT
    g.deputado_id,
    g.nome_parlamentar,
    g.partido,
    g.uf,
    coalesce(u.regiao, 'Não informada')      AS regiao,
    dep.sexo,
    g.lancamentos,
    g.fornecedores_distintos,
    g.despesa_liquida,
    g.ticket_medio_nota,
    rank() OVER (ORDER BY g.despesa_liquida DESC) AS posicao_maior_gasto,
    g.meses_exercicio,
    u.limite_mensal_cota,
    round(100.0 * g.despesa_liquida / (u.limite_mensal_cota * g.meses_exercicio), 2) AS pct_teto_utilizado,
    m.nome_fornecedor                         AS maior_fornecedor,
    round(100.0 * m.despesa_fornecedor / g.despesa_liquida, 2) AS pct_maior_fornecedor
FROM gastos_deputado        AS g
LEFT JOIN refined.deputados AS dep ON dep.deputado_id = g.deputado_id
LEFT JOIN refined.cotas_uf  AS u   ON u.uf = g.uf
LEFT JOIN maior_fornecedor  AS m   ON m.deputado_id = g.deputado_id
ORDER BY posicao_maior_gasto, g.deputado_id
