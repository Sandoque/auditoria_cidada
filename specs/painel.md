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
- **Faixa 1 (Sete cartões executivos)**: cada cartão tem rótulo, valor e uma linha de detalhe, todos lidos de `marts.kpis`. Definidos uma única vez em `painel.cartoes(kpi)` e desenhados por `painel.html_cartoes()`, que `app.py` e `relatorio.py` compartilham.
  1. `Despesa líquida · válida`: `reais_compacto(despesa_total_reais)` · detalhe: valor exato em reais
  2. `Ticket médio · por nota`: `ticket_medio_nota` · detalhe: mediana (`ticket_mediana_nota`)
  3. `Taxa de glosa · % cortado`: `pct_glosado` (2 casas) · detalhe: `valor_glosado_total` cortados
  4. `Fornecedores recorrentes · 2+`: `pct_fornecedores_recorrentes` (2 casas) · detalhe: de `fornecedores_distintos` fornecedores
  5. `Fora do CEIS · % do valor`: `pct_valor_regular` (2 casas) · detalhe: `despesa_fornecedores_ceis` pagos a fornecedores no CEIS
     - *Motivo do rótulo*: não constar no CEIS não prova que o gasto é regular; o rótulo antigo ("Valor regular") afirmava mais do que o dado sustenta.
  6. `Pago em sanção vigente · CEIS`: `despesa_sancao_vigente` · detalhe: quanto é `restrita` e quanto é `sem_info`
  7. `Sanção vigente · alcance federal` (**âmbar**): `despesa_sancao_vigente_federal` · detalhe: notas e fornecedores
     - *Motivo*: só o cartão 7 fica em âmbar. A maior parte do valor do cartão 6 vem de sanções que o próprio CEIS restringe a outro órgão ou esfera (regra em `specs/marts.md`, seção 6).
- **Subtítulo-resposta em todos os gráficos**: abaixo do título, uma frase com a resposta da pergunta, montada só selecionando linhas do mart (maior, menor, primeira linha que cruza um limite). Nenhuma soma ou divisão na tela; quando o percentual é necessário, ele vem pronto do SQL (`pct_total`).
- **Faixa 2 (Largura inteira)**:
  - `01 · Desembolso mensal da Cota Parlamentar` (linha com marcadores) · subtítulo: mês de pico e mês de piso.
- **Faixa 3 (Três colunas iguais)**:
  - `02 · Despesa por categoria (Top 10)` (barras horizontais, maior em cima) · subtítulo: categoria líder e `pct_total`
  - `10 · Despesa por partido político (Top 10)` (barras horizontais, maior em cima) · subtítulo: partido líder, `pct_total` e tamanho da bancada
  - `06 · Gasto anual médio por deputado por UF (Top 10)` (barras horizontais, maior em cima) · subtítulo: UF líder e seu `limite_mensal_cota`
- **Faixa 4 (Três colunas iguais)**:
  - `07 · Pago em sanção vigente (Top 10)` (barras horizontais de `valor_recebido_em_vigencia`, só fornecedores com valor em vigência, maior em cima). A cor mostra o `alcance_sancao_vigente`, com legenda: âmbar = federal, âmbar hachurado = sem informação, cinza = restrita.
    - *Motivo*: ordenado pelo total recebido, um fornecedor pago só fora da vigência achatava todas as barras de risco e escondia a cor do alcance.
  - `08 · Taxa de glosa por categoria (Top 10)` (barras horizontais de `pct_valor_glosado`, maior em cima) · subtítulo: maior taxa e maior corte em reais
    - *Motivo*: em reais, o ranking de glosa repete o tamanho de cada categoria; a taxa mostra onde a Câmara mais corta.
  - `09 · Concentração de Pareto dos fornecedores` (curva de `pct_acumulado` por `posicao`, com linha horizontal tracejada em 80%). A anotação da linha e o subtítulo usam a primeira `posicao` com `pct_acumulado >= 80`, lida do mart, nunca um número fixo no código.

### 4. FORMATAÇÃO PURA (`painel.py`)
- `reais(valor, casas=2) -> "R$ 1.003.862,14"`
- `reais_compacto(valor) -> "R$ 215,11 mi"`, `"R$ 192,1 mil"` ou `"R$ 840,00"` (só troca a unidade de exibição)
- `pct(valor, casas=1) -> "93,2%"`
- `numero(valor, casas=0) -> "96.470"`
- Milhar com ponto e decimal com vírgula, sem usar `locale` do sistema operacional.

### 5. RELATÓRIO HTML (`relatorio.py`)
- Reaproveita `painel.ler()`, `painel.cartoes()`, `painel.html_cartoes()` e as sete funções de gráficos de `painel.py`.
- Grava `relatorio.html` na raiz com menos de 200 KB (`include_plotlyjs="cdn"` apenas no primeiro gráfico e `div_id` fixos `"g01"` a `"g07"`).
- Rodapé com carimbo `"Dados de DD/MM/AAAA HH:MM"`.
