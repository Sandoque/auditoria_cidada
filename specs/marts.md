# Spec da Etapa 3 — Executor de Marts (`pipeline/marts.py`) e Qualidade de Dados (`pipeline/qualidade.py`)

## CONTEXTO
Construção da camada `marts` do pipeline de Auditoria Cidadã e Compliance. Os doze arquivos `.sql` moram em `sql/marts/` e contêm toda a regra de negócio, com o grão declarado na primeira linha de cada arquivo e em cada CTE. `pipeline/marts.py` apenas orquestra a execução transacional dos arquivos `.sql`.

## STACK
- Python >= 3.12, `uv`, `DuckDB` (`auditoria.duckdb` na raiz do projeto)
- O que já existe: `pipeline/db.py`, o schema `refined` com quatro tabelas (`despesas_ceap`, `deputados`, `sancoes_ceis`, `cotas_uf`) e a pasta `sql/marts/` com arquivos `NN_nome.sql`.

## ARTEFATOS A PRODUZIR
1. `pipeline/marts.py`, executável com `uv run python -m pipeline.marts`.
2. `pipeline/qualidade.py`, executável com `uv run python -m pipeline.qualidade` (testes de qualidade de dados sobre o banco gravado, conforme seção 09 da Aula 4).

---

## SPEC DO `pipeline/marts.py`

### 1. ESCOPO
- Lê de `refined`, escreve no schema `marts`. Nunca escreve em `raw` nem em `refined`.
- O schema `marts` é apagado e recriado a cada execução (`DROP SCHEMA IF EXISTS marts CASCADE`).
  - *Motivo*: um mart cujo arquivo `.sql` foi apagado não pode continuar existindo como tabela órfã no banco.

### 2. UM ARQUIVO, UMA TABELA
- Lê todos os arquivos `sql/marts/*.sql` em ordem alfabética.
- Nome da tabela = nome do arquivo sem a extensão `.sql` e sem o prefixo numérico `NN_`:
  - `sql/marts/01_gastos_mensais.sql` -> `marts.gastos_mensais`
- Executa `CREATE TABLE marts.<nome> AS <conteúdo do arquivo>`.
- Remove apenas espaços em branco e um ponto e vírgula final (`;`) do conteúdo, sem alterar nem montar SQL em Python.

### 3. SAÍDA NA TELA
- Uma linha por mart com a contagem lida do banco (milhar com ponto):
  - `✓ marts.gastos_mensais            15 linhas`
- Linha final com a quantidade de marts e a soma total de linhas. `stdout` em `utf-8`.

### 4. ERRO E TRANSAÇÃO
- Antes de tudo: se faltar qualquer uma das quatro tabelas em `refined`, lista quais, orienta a rodar `uv run python -m pipeline.transformacao` e encerra com `sys.exit(1)`.
- Se `sql/marts/` não existir ou não tiver nenhum arquivo `.sql`, avisa e encerra com `sys.exit(1)`.
- Antes de executar qualquer SQL: se houver arquivo sem prefixo `NN_` (dois dígitos + underscore) ou dois arquivos que gerem o mesmo nome de tabela, lista os arquivos inválidos e encerra com `sys.exit(1)`.
- Tudo roda em uma única transação (`BEGIN TRANSACTION` ... `COMMIT`): se qualquer `.sql` tiver erro de sintaxe ou voltar com `0` linhas (mart vazio), faz `ROLLBACK`, mostra o nome do arquivo e o erro, e encerra com `sys.exit(1)`.
  - *Motivo*: se um passo falhar, o schema `marts` volta exatamente ao estado da última execução bem-sucedida, sem deixar um banco pela metade.

---

## SPEC DAS REGRAS DE SANÇÃO (marts `03`, `07` e `11`)

### 5. VIGÊNCIA POR SANÇÃO, NÃO POR ENVELOPE
- Uma nota está **em sanção vigente** quando existe ao menos uma sanção do mesmo `documento_sancionado` cuja janela `[data_inicio_sancao, coalesce(data_fim_sancao, DATE '2099-12-31')]` contém a data da nota (`coalesce(data_emissao::DATE, make_date(ano_competencia, mes_competencia, 1))`).
  - *Motivo*: o envelope `min(início)`–`max(fim)` por fornecedor marcava como vigente uma nota emitida no intervalo **entre** duas sanções distintas.
- A busca usa subconsulta escalar correlacionada (`SELECT max(...) ... WHERE ...`), que devolve no máximo um valor por nota. O grão da nota nunca é multiplicado pelo número de sanções.

### 6. ALCANCE DA SANÇÃO VIGENTE
- Cada sanção recebe um alcance a partir de `abrangencia_sancao` e `esfera_orgao_sancionador`:

| Alcance | Regra | Leitura |
| :--- | :--- | :--- |
| `federal` | `'Todas as Esferas em todos os Poderes'`, ou `'Em todos os Poderes da Esfera do órgão sancionador'` com esfera `FEDERAL` | O próprio CEIS diz que a sanção alcança a esfera federal, onde está a Câmara. |
| `restrita` | `'No órgão sancionador'` ou `'Em outro órgão'`; ou `'Em todos os Poderes da Esfera…'` / `'Na Esfera e no Poder…'` com esfera `ESTADUAL` ou `MUNICIPAL` | O próprio CEIS diz que a sanção vale só em outro órgão ou em outra esfera. |
| `sem_informacao` | Todo o resto (`'Sem Informação'`, esfera nula, `'Na Esfera e no Poder…'` com esfera `FEDERAL`, valores novos) | O cadastro não permite afirmar o alcance. O CEIS não informa o Poder do órgão sancionador. |

- Quando mais de uma sanção está vigente na data da nota, vale o alcance mais amplo: `federal` > `sem_informacao` > `restrita`.
  - *Motivo*: só se afirma "restrita" quando o cadastro diz isso explicitamente. Qualquer dúvida cai em `sem_informacao`, nunca em `restrita`.
- Colunas novas:
  - `marts.conformidade_ceis` e `marts.kpis`: `lancamentos_sancao_vigente_*` e `despesa_sancao_vigente_*` para `federal`, `sem_info` e `restrita`; `marts.kpis` também traz `fornecedores_sancao_vigente_federal` e `valor_glosado_total`.
  - `marts.fornecedores_sancionados`: `alcance_sancao_vigente` (o alcance mais amplo entre as notas do fornecedor em vigência; `NULL` quando nenhuma nota caiu em vigência).
  - `marts.gastos_por_categoria`: `pct_total` (participação da categoria na despesa líquida).

### 7. QUALIDADE (`pipeline/qualidade.py`)
- **As partes somam o todo**: em `marts.conformidade_ceis`, `federal + sem_info + restrita = despesa_sancao_vigente`, em valor e em lançamentos.
- **Dois caminhos concordam**: os três valores por alcance de `marts.conformidade_ceis` batem centavo por centavo com os de `marts.kpis`.
