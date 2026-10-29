-- Quais parlamentares mais utilizaram a Cota Parlamentar, quanto do teto usaram e quão concentrado foi o gasto?
-- Grão: um deputado federal com lançamento válido em um ano (ano, deputado_id).
-- Exclui os lançamentos institucionais de Lideranças Partidárias (onde deputado_id é NULL).
-- Teto, partido e UF do ano vêm de marts.teto_deputado_ano (único cálculo do teto).
WITH gastos_deputado AS (
    -- Grão: (ano, deputado_id).
    SELECT
        d.ano_competencia                      AS ano,
        d.deputado_id,
        max(d.nome_parlamentar)                AS nome_parlamentar,
        count(*)                               AS lancamentos,
        count(DISTINCT d.documento_fornecedor) AS fornecedores_distintos,
        round(avg(d.valor_liquido), 2)         AS ticket_medio_nota
    FROM refined.despesas_ceap AS d
    WHERE d.valor_liquido > 0
      AND d.deputado_id IS NOT NULL
    GROUP BY d.ano_competencia, d.deputado_id
),
gasto_deputado_fornecedor AS (
    -- Grão: (ano, deputado_id, documento_fornecedor).
    SELECT
        ano_competencia      AS ano,
        deputado_id,
        documento_fornecedor,
        max(nome_fornecedor) AS nome_fornecedor,
        sum(valor_liquido)   AS despesa_fornecedor
    FROM refined.despesas_ceap
    WHERE valor_liquido > 0
      AND deputado_id IS NOT NULL
    GROUP BY ano_competencia, deputado_id, documento_fornecedor
),
maior_fornecedor AS (
    -- Grão: (ano, deputado_id). O fornecedor que mais recebeu dele no ano; empate vai para o menor documento.
    SELECT ano, deputado_id, nome_fornecedor, despesa_fornecedor
    FROM gasto_deputado_fornecedor
    QUALIFY row_number() OVER (
        PARTITION BY ano, deputado_id ORDER BY despesa_fornecedor DESC, documento_fornecedor
    ) = 1
)
SELECT
    g.ano,
    g.deputado_id,
    g.nome_parlamentar,
    t.partido,
    t.uf,
    coalesce(u.regiao, 'Não informada')      AS regiao,
    dep.sexo,
    g.lancamentos,
    g.fornecedores_distintos,
    t.despesa_liquida,
    g.ticket_medio_nota,
    rank() OVER (PARTITION BY g.ano ORDER BY t.despesa_liquida DESC) AS posicao_maior_gasto,
    t.meses_exercicio,
    t.dias_exercicio,
    t.teto_periodo,
    t.pct_teto_utilizado,
    t.fonte_periodo,
    m.nome_fornecedor                         AS maior_fornecedor,
    round(100.0 * m.despesa_fornecedor / t.despesa_liquida, 2) AS pct_maior_fornecedor
FROM gastos_deputado          AS g
JOIN marts.teto_deputado_ano  AS t   ON t.ano = g.ano AND t.deputado_id = g.deputado_id
LEFT JOIN refined.deputados   AS dep ON dep.deputado_id = g.deputado_id
LEFT JOIN refined.cotas_uf    AS u   ON u.uf = t.uf
LEFT JOIN maior_fornecedor    AS m   ON m.ano = g.ano AND m.deputado_id = g.deputado_id
ORDER BY g.ano, posicao_maior_gasto, g.deputado_id
