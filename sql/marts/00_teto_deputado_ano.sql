-- Quanto cada deputado podia gastar no ano (teto proporcional aos dias de efetivo exercício) e quanto usou?
-- Grão: um deputado em um ano (ano, deputado_id), só deputados com lançamento válido no ano.
-- Base dos marts 04, 06, 10 e 11: é o único lugar onde o teto da cota é calculado (specs/multianual.md, seção 3).
WITH gasto_deputado_ano AS (
    -- Grão: (ano, deputado_id). O intervalo aproximado só é usado como reserva.
    SELECT
        ano_competencia                                               AS ano,
        deputado_id,
        max(uf)                                                       AS uf,
        sum(valor_liquido)                                            AS despesa_liquida,
        make_date(ano_competencia, min(mes_competencia), 1)           AS inicio_aproximado,
        last_day(make_date(ano_competencia, max(mes_competencia), 1)) AS fim_aproximado
    FROM refined.despesas_ceap
    WHERE valor_liquido > 0
      AND deputado_id IS NOT NULL
    GROUP BY ano_competencia, deputado_id
),
partido_recente AS (
    -- Grão: (ano, deputado_id). Partido do lançamento mais recente no ano (troca na janela partidária).
    SELECT ano_competencia AS ano, deputado_id, partido
    FROM refined.despesas_ceap
    WHERE valor_liquido > 0
      AND deputado_id IS NOT NULL
    QUALIFY row_number() OVER (
        PARTITION BY ano_competencia, deputado_id
        ORDER BY mes_competencia DESC, data_emissao DESC NULLS LAST, partido
    ) = 1
),
corte_ano AS (
    -- Grão: um ano. Último dia do último mês de competência com dados; num ano em curso, o teto vai até aí.
    SELECT
        ano_competencia                                               AS ano,
        last_day(make_date(ano_competencia, max(mes_competencia), 1)) AS ultimo_dia
    FROM refined.despesas_ceap
    GROUP BY ano_competencia
),
transicoes AS (
    -- Grão: um evento do histórico de mandato que muda o estado ('entra' ou 'sai').
    -- 'Contém' e não 'começa com': a API grava reentradas como "DIVERSO - ... / Entrada - Reassunção".
    SELECT
        deputado_id,
        data_hora,
        CASE
            WHEN descricao_status LIKE '%Entrada - %' THEN 'entra'
            WHEN descricao_status LIKE '%Saída - %'
             AND descricao_status NOT LIKE '%Licença para Tratamento de Saúde%' THEN 'sai'
        END AS transicao
    FROM refined.historico_deputados
),
periodos_exercicio AS (
    -- Grão: um período de exercício, da entrada até a próxima saída (o dia do afastamento conta, art. 11).
    SELECT deputado_id, data_inicio, coalesce(proxima_saida, DATE '9999-12-31') AS data_fim
    FROM (
        SELECT
            deputado_id,
            transicao,
            data_hora::DATE AS data_inicio,
            min(data_hora::DATE) FILTER (WHERE transicao = 'sai') OVER (
                PARTITION BY deputado_id ORDER BY data_hora
                ROWS BETWEEN 1 FOLLOWING AND UNBOUNDED FOLLOWING
            ) AS proxima_saida
        FROM transicoes
        WHERE transicao IS NOT NULL
    )
    WHERE transicao = 'entra'
),
calendario AS (
    -- Grão: um dia de cada ano com dados, até o corte do ano.
    SELECT ano, unnest(generate_series(make_date(ano, 1, 1), ultimo_dia, INTERVAL 1 DAY))::DATE AS dia
    FROM corte_ano
),
dias_oficiais AS (
    -- Grão: (ano, deputado_id, dia) de efetivo exercício, só de quem tem despesa no ano.
    SELECT DISTINCT g.ano, g.deputado_id, c.dia
    FROM gasto_deputado_ano AS g
    JOIN calendario         AS c ON c.ano = g.ano
    JOIN periodos_exercicio AS p ON p.deputado_id = g.deputado_id
                                AND c.dia BETWEEN p.data_inicio AND p.data_fim
),
dias_exercicio AS (
    -- Grão: (ano, deputado_id, dia). Reserva aproximada só para quem não tem nenhum dia oficial no ano.
    SELECT ano, deputado_id, dia, 'oficial' AS fonte_periodo
    FROM dias_oficiais
    UNION ALL
    SELECT g.ano, g.deputado_id, c.dia, 'aproximado' AS fonte_periodo
    FROM gasto_deputado_ano AS g
    JOIN calendario         AS c ON c.ano = g.ano
                                AND c.dia BETWEEN g.inicio_aproximado AND g.fim_aproximado
    WHERE NOT EXISTS (
        SELECT 1 FROM dias_oficiais AS o WHERE o.ano = g.ano AND o.deputado_id = g.deputado_id
    )
),
limites_vigencia AS (
    -- Grão: uma UF em um período de vigência do limite (o fim é a véspera da vigência seguinte).
    SELECT
        uf,
        vigencia_inicio,
        coalesce(
            lead(vigencia_inicio) OVER (PARTITION BY uf ORDER BY vigencia_inicio) - 1,
            DATE '9999-12-31'
        ) AS vigencia_fim,
        limite_mensal_cota
    FROM refined.limites_cota_uf
),
teto AS (
    -- Grão: (ano, deputado_id). Cada dia vale o limite mensal vigente naquele dia ÷ dias do mês.
    SELECT
        d.ano,
        d.deputado_id,
        max(d.fonte_periodo)                                         AS fonte_periodo,
        count(*)                                                     AS dias_exercicio,
        count(*) FILTER (WHERE l.limite_mensal_cota IS NULL)         AS dias_sem_limite,
        round(sum(1.0 / day(last_day(d.dia))), 2)                    AS meses_exercicio,
        round(sum(l.limite_mensal_cota / day(last_day(d.dia))), 2)   AS teto_periodo
    FROM dias_exercicio          AS d
    JOIN gasto_deputado_ano      AS g ON g.ano = d.ano AND g.deputado_id = d.deputado_id
    LEFT JOIN limites_vigencia   AS l ON l.uf = g.uf AND d.dia BETWEEN l.vigencia_inicio AND l.vigencia_fim
    GROUP BY d.ano, d.deputado_id
),
limite_no_corte AS (
    -- Grão: (ano, uf). Limite mensal vigente no último dia com dados do ano.
    SELECT c.ano, l.uf, l.limite_mensal_cota
    FROM corte_ano        AS c
    JOIN limites_vigencia AS l ON c.ultimo_dia BETWEEN l.vigencia_inicio AND l.vigencia_fim
)
SELECT
    g.ano,
    g.deputado_id,
    g.uf,
    p.partido,
    g.despesa_liquida,
    t.dias_exercicio,
    t.meses_exercicio,
    t.teto_periodo,
    round(100.0 * g.despesa_liquida / nullif(t.teto_periodo, 0), 2) AS pct_teto_utilizado,
    t.fonte_periodo,
    t.dias_sem_limite,
    lc.limite_mensal_cota                                           AS limite_mensal_vigente
FROM gasto_deputado_ano    AS g
JOIN teto                  AS t  ON t.ano = g.ano AND t.deputado_id = g.deputado_id
JOIN partido_recente       AS p  ON p.ano = g.ano AND p.deputado_id = g.deputado_id
LEFT JOIN limite_no_corte  AS lc ON lc.ano = g.ano AND lc.uf = g.uf
ORDER BY g.ano, g.deputado_id
