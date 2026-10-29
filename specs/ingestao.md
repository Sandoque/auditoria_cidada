# Spec da Etapa 1 — Ingestão (`pipeline/db.py`, `pipeline/ingestao.py`, `ui.py`)

> **Atualizada pela Etapa 6** (`specs/multianual.md`): a ingestão passa a exigir sete arquivos (`limites_cota_uf.csv.gz` e `historico_deputados.csv.gz` são novos) e `despesas_ceap.csv.gz` traz todos os anos desde 2025. As contagens dos critérios de aceite abaixo são as do retrato de 2025.

## CONTEXTO
Construção de um pipeline de Auditoria Cidadã e Compliance sobre dados públicos oficiais da Câmara dos Deputados (CEAP 2025 e Cadastro de Deputados), da Controladoria-Geral da União — CGU (CEIS e CNEP) e do IBGE (UFs e limites mensais de cota). Trabalho com *spec-driven development*: a spec abaixo é a fonte da verdade e o código é consequência dela.

## STACK
- Python >= 3.12, dependências gerenciadas com `uv`
- `pandas` para ler os arquivos `.csv.gz`
- `DuckDB` como banco analítico local, arquivo `auditoria.duckdb` na raiz do projeto
- Nenhum orquestrador externo; scripts executáveis pela linha de comando

## ARTEFATOS A PRODUZIR
1. `pipeline/db.py`: módulo de conexão que as quatro etapas do projeto importam.
2. `pipeline/ingestao.py`: executável com `uv run python -m pipeline.ingestao`.
3. `ui.py`: na raiz do projeto, executável com `uv run python ui.py`.

---

## SPEC DO `pipeline/db.py`
Expõe exatamente isto, com estes nomes:
- `PASTA_RAW`: `Path` da pasta `raw/` com os cinco arquivos `.csv.gz`
- `conectar()`: abre o `auditoria.duckdb`, criando se faltar
- `criar_schema(con, nome)`: `CREATE SCHEMA IF NOT EXISTS`
- `gravar(con, df, schema, tabela)`: grava e devolve a contagem lida do banco

### Regras e Motivos
- **D1. CAMINHOS**: `PASTA_RAW` e o `auditoria.duckdb` são resolvidos a partir da localização do próprio `db.py` (`Path(__file__).resolve().parent.parent`), nunca do diretório corrente.
  - *Motivo*: rodar o script de outra pasta não pode criar um `auditoria.duckdb` vazio no lugar errado, que pareceria ingestão quebrada.
- **D2. TRÊS FUNÇÕES E UMA CONSTANTE, NADA MAIS**: `db.py` não lê CSV, não conhece nome de tabela, não imprime nada e não converte tipo.
  - *Motivo*: todas as etapas importam este arquivo; regra de negócio escondida aqui valeria para todas sem aparecer em nenhuma spec.
- **D3. `gravar`**: Recria a tabela (`CREATE OR REPLACE TABLE schema.tabela`) com as colunas e os tipos do DataFrame, sem alterar nada (`VARCHAR` continua `VARCHAR`, nulo continua `NULL`). Não deixa view ou tabela temporária para trás. Devolve `SELECT count(*)` da tabela recém-gravada, lido do banco.
  - *Motivo*: a contagem que aparece na tela tem que ser a do que foi efetivamente gravado no disco, não a do que estava em memória.
- **D4. CONEXÃO**: `conectar()` devolve a conexão aberta; quem chama é quem fecha. `db.py` não guarda conexão global.

---

## SPEC DA INGESTÃO (`pipeline/ingestao.py`)

### 1. ESCOPO E NOMES
Schema de destino: `raw`
Mapa arquivo -> tabela, completo e literal:
- `despesas_ceap.csv.gz` -> `raw.despesas_ceap`
- `deputados.csv.gz` -> `raw.deputados`
- `sancoes_ceis.csv.gz` -> `raw.sancoes_ceis`
- `sancoes_cnep.csv.gz` -> `raw.sancoes_cnep`
- `cotas_uf.csv.gz` -> `raw.cotas_uf`

### 2. PROIBIÇÕES
Nenhuma conversão de tipo. Nenhuma linha descartada ou deduplicada. Nenhum nome de coluna alterado. Nenhum valor corrigido, preenchido ou normalizado. Data continua texto, dinheiro continua texto, CNPJ/CPF continua texto, nulo continua nulo.
- *Motivo*: a fronteira entre "o dado que chegou do governo" e "o dado que decidimos transformar" precisa existir na passagem de `raw` para `refined` (etapa 2).

### 3. REEXECUÇÃO (IDEMPOTÊNCIA)
Rodar dez vezes dá o mesmo resultado que rodar uma: cada tabela é recriada (`CREATE OR REPLACE TABLE`), nunca acrescentada.

### 4. LEITURA DO ARQUIVO
- `encoding="utf-8"` declarado, nunca adivinhado.
- `.csv.gz` lidos direto, sem descompactar.
- Campo vazio vira `NULL` (`keep_default_na=False`, `na_values=[""]`), nunca string vazia.

### 5. TIPAGEM
Toda coluna entra como texto (`dtype=str`), inferência desligada.
- *Motivo*: inferência numérica lê CNPJ/CPF com zero à esquerda (`08532429000131` ou `03316005870`) como inteiro e apaga o zero inicial sem aviso, destruindo os JOINs de auditoria.

### 6. SAÍDA NA TELA
Uma linha por tabela, com nome qualificado e contagem de linhas vinda do banco, milhar separado por ponto, e uma linha final com o total (`204.567 linhas`). `stdout` reconfigurado para `utf-8`.

### 7. ERRO
Antes de abrir o banco, verifica se os cinco arquivos existem em `PASTA_RAW`. Faltando qualquer um: lista os que faltam, diz em que pasta procurou e encerra com `sys.exit(1)` sem ingerir parcialmente.

### CRITÉRIOS DE ACEITE (ingestão)
- A execução imprime cinco linhas (`raw.despesas_ceap`: 171.059, `raw.deputados`: 7.889, `raw.sancoes_ceis`: 23.739, `raw.sancoes_cnep`: 1.853, `raw.cotas_uf`: 27) e um total de `204.567 linhas`.
- Rodar duas vezes seguidas imprime exatamente a mesma coisa.
- `DESCRIBE raw.despesas_ceap` devolve todas as 32 colunas como `VARCHAR`.
- Remover um arquivo de `raw/` faz o script parar com `SystemExit(1)` antes de gravar qualquer tabela.

---

## SPEC DO `ui.py`
- **U1. O QUE FAZ**: Abre o `auditoria.duckdb` da raiz do projeto, instala/carrega a extensão `ui` (`INSTALL ui; LOAD ui;`) e chama `CALL start_ui()` (`http://localhost:4213`).
- **U2. FICA DE PÉ ATÉ CTRL+C**: Mantém o processo rodando e sai limpo no `Ctrl+C`, fechando a conexão sem traceback.
- **U3. NÃO CRIA BANCO**: Se `auditoria.duckdb` não existir, avisa que é preciso rodar `uv run python -m pipeline.ingestao` antes e encerra com `sys.exit(1)`.
- **U4. SEPARAÇÃO**: Não importa `pipeline/ingestao.py` nem `pipeline/db.py`.
