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
