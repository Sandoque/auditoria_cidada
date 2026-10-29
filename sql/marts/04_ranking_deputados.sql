-- Quais parlamentares mais utilizaram a Cota Parlamentar e qual sua posição no ranking?
-- Grão: um deputado federal com lançamento válido (deputado_id IS NOT NULL).
-- Exclui os 937 lançamentos institucionais de Lideranças Partidárias (onde deputado_id é NULL).
WITH gastos_deputado AS (
    -- Grão: um deputado_id.
    SELECT
        d.deputado_id,
        max(d.nome_parlamentar)              AS nome_parlamentar,
        max(d.partido)                       AS partido,
        max(d.uf)                            AS uf,
        count(*)                             AS lancamentos,
        count(DISTINCT d.documento_fornecedor) AS fornecedores_distintos,
        sum(d.valor_liquido)                 AS despesa_liquida,
        round(avg(d.valor_liquido), 2)       AS ticket_medio_nota
    FROM refined.despesas_ceap AS d
    WHERE d.valor_liquido > 0
      AND d.deputado_id IS NOT NULL
    GROUP BY d.deputado_id
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
    rank() OVER (ORDER BY g.despesa_liquida DESC) AS posicao_maior_gasto
FROM gastos_deputado        AS g
LEFT JOIN refined.deputados AS dep ON dep.deputado_id = g.deputado_id
LEFT JOIN refined.cotas_uf  AS u   ON u.uf = g.uf
ORDER BY posicao_maior_gasto, g.deputado_id
