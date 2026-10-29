-- Que fração dos fornecedores concentra 80% dos recursos da Cota Parlamentar (Curva de Pareto)?
-- Grão: um fornecedor com lançamento válido (documento_fornecedor), ordenado do maior para o menor.
-- documento_fornecedor desempata valores idênticos para garantir ordem determinística.
WITH receita_fornecedor AS (
    -- Grão: um fornecedor (documento_fornecedor).
    SELECT
        documento_fornecedor,
        max(nome_fornecedor) AS nome_fornecedor,
        count(*)             AS lancamentos,
        sum(valor_liquido)   AS despesa_liquida
    FROM refined.despesas_ceap
    WHERE valor_liquido > 0
    GROUP BY documento_fornecedor
)
SELECT
    documento_fornecedor,
    nome_fornecedor,
    lancamentos,
    despesa_liquida,
    row_number() OVER (ORDER BY despesa_liquida DESC, documento_fornecedor) AS posicao,
    round(
        100.0 * sum(despesa_liquida) OVER (ORDER BY despesa_liquida DESC, documento_fornecedor)
        / sum(despesa_liquida) OVER (),
        2
    ) AS pct_acumulado
FROM receita_fornecedor
ORDER BY posicao
