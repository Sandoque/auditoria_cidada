# Spec da Etapa 4 — Painel em Python (`painel.py`, `app.py`) e Relatório HTML (`relatorio.py`)

## CONTEXTO
Construção da camada de apresentação do pipeline de Auditoria Cidadã e Compliance a partir do rascunho em `design/rascunho.png` e dos doze marts do schema `marts`.

## STACK
- Python >= 3.12, `uv`, `DuckDB` (`auditoria.duckdb` na raiz do projeto)
- `streamlit` e `plotly` (`plotly.express` / `plotly.graph_objects`)

## ARTEFATOS A PRODUZIR
1. `painel.py`: leitura em somente leitura, formatação independente de locale e funções de gráficos Plotly (não importa `streamlit`).
2. `app.py`: aplicação Streamlit (`uv run streamlit run app.py`).
3. `relatorio.py`: gerador do painel estático autocontido em `relatorio.html` (`uv run python relatorio.py`).

---

## SPEC

### 1. LEITURA (`painel.py`)
- `ler(marts) -> dict[str, pd.DataFrame]`: para cada nome na lista, executa exclusivamente `SELECT * FROM marts.<nome>`.
- Conexão aberta com `duckdb.connect(..., read_only=True)` e fechada dentro de `ler()`.
  - *Motivo*: não prender lock no arquivo `auditoria.duckdb`, permitindo rodar `uv run python -m pipeline.marts` com o painel aberto.

### 2. NENHUM CÁLCULO NA TELA
- Proibido realizar agregações ou junções em `painel.py` e `app.py`. Permitido apenas: ordenar, filtrar linhas, `head(n)`, renomear colunas para exibição e formatar texto.

### 3. LAYOUT (`app.py` e `relatorio.html`) — Leitura em Z (4 Faixas)
- **Cabeçalho**: Título `"Auditoria Cidadã · Cota Parlamentar (CEAP 2025) × Sanções CEIS/CGU"` à esquerda; filtro de período de competência à direita.
- **Faixa 1 (Sete cartões executivos)**:
  1. `Despesa líquida` (`kpis.despesa_total_reais`, em reais)
  2. `Ticket médio · por nota válida` (`kpis.ticket_medio_nota`, em reais)
  3. `Taxa de glosa · % cortado pela Câmara` (`kpis.pct_glosado`, 2 casas)
  4. `Fornecedores recorrentes · 2+ pagamentos` (`kpis.pct_fornecedores_recorrentes`, 2 casas)
  5. `Valor regular · fora do CEIS` (`kpis.pct_valor_regular`, 2 casas)
  6. `Pago em sanção ativa · CEIS vigente` (`kpis.despesa_sancao_vigente`, em reais)
  7. `Notas em sanção ativa · CEIS vigente` (`kpis.lancamentos_sancao_vigente`, inteiro)
- **Faixa 2 (Largura inteira)**:
  - `01 · Desembolso mensal da Cota Parlamentar` (linha com marcadores).
- **Faixa 3 (Três colunas iguais)**:
  - `02 · Despesa por categoria (Top 10)` (barras horizontais, maior em cima)
  - `10 · Despesa por partido político (Top 10)` (barras horizontais, maior em cima)
  - `06 · Gasto anual médio por deputado por UF (Top 10)` (barras horizontais, maior em cima)
- **Faixa 4 (Três colunas iguais)**:
  - `07 · Fornecedores sancionados no CEIS com recebimento (Top 10)` (barras horizontais, maior em cima)
  - `08 · Glosas aplicadas por categoria (Top 10)` (barras horizontais, maior em cima)
  - `09 · Concentração de Pareto dos fornecedores` (curva de `pct_acumulado` por `posicao`, com linha horizontal tracejada em 80%).

### 4. FORMATAÇÃO PURA (`painel.py`)
- `reais(valor, casas=2) -> "R$ 1.003.862,14"`
- `pct(valor, casas=1) -> "93,2%"`
- `numero(valor, casas=0) -> "96.470"`
- Milhar com ponto e decimal com vírgula, sem usar `locale` do sistema operacional.

### 5. RELATÓRIO HTML (`relatorio.py`)
- Reaproveita `painel.ler()`, `painel.reais/pct/numero` e as sete funções de gráficos de `painel.py`.
- Grava `relatorio.html` na raiz com menos de 200 KB (`include_plotlyjs="cdn"` apenas no primeiro gráfico e `div_id` fixos `"g01"` a `"g07"`).
- Rodapé com carimbo `"Dados de DD/MM/AAAA HH:MM"`.
