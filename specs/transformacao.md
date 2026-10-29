# Spec da Etapa 2 — Transformação (`pipeline/transformacao.py`)

> **Atualizada pela Etapa 6** (`specs/multianual.md`): entram `refined.limites_cota_uf` e `refined.historico_deputados`, e `refined.cotas_uf` perde `limite_mensal_cota`. As contagens dos critérios de aceite abaixo são as do retrato de 2025.

## CONTEXTO
Construção da camada `refined` do pipeline de Auditoria Cidadã e Compliance sobre dados da Câmara dos Deputados (CEAP 2025 e Deputados), CGU (CEIS) e IBGE (`cotas_uf`). Trabalho com *spec-driven development*: a spec abaixo é a fonte da verdade e o código é consequência dela.

## STACK
- Python >= 3.12, `uv`, `DuckDB` (`auditoria.duckdb` na raiz do projeto)
- O que já existe: `pipeline/db.py` (`conectar()`, `criar_schema(con, nome)`) e o schema `raw` com cinco tabelas em `VARCHAR`.

## ARTEFATO A PRODUZIR
`pipeline/transformacao.py`, executável com:
```bash
uv run python -m pipeline.transformacao
```

---

## SPEC

### 1. ESCOPO
Lê de `raw`, escreve no schema `refined`. Nunca escreve em `raw`.
- **Entram quatro tabelas**: `despesas_ceap`, `deputados`, `sancoes_ceis`, `cotas_uf`.
- **Fica de fora**: `sancoes_cnep` (nenhum mart principal depende dela; possui spec própria de investigação em `specs/sancoes_cnep.md`, seguindo a separação de escopo do curso).

### 2. NOMES E PADRONIZAÇÃO DE CHAVES
Colunas selecionadas e renomeadas para português, `snake_case`, com o mapa completo abaixo:

- **`refined.despesas_ceap`**:
  - `ideDocumento` -> `documento_id`
  - `txNomeParlamentar` -> `nome_parlamentar`
  - `ideCadastro` -> `deputado_id`
  - `NULLIF(sgUF, 'NA')` -> `uf` *(Motivo: nos 937 gastos de Lideranças Partidárias onde `ideCadastro` é nulo, a Câmara grava a string literal `'NA'` em `sgUF`; converter `'NA'` para `NULL` evita criar uma 28.ª UF fictícia)*
  - `sgPartido` -> `partido`
  - `codLegislatura` -> `legislatura_id`
  - `numSubCota` -> `subcota_id`
  - `txtDescricao` -> `categoria_despesa`
  - `txtFornecedor` -> `nome_fornecedor`
  - `regexp_replace(txtCNPJCPF, '[^0-9]', '', 'g')` -> `documento_fornecedor` *(Motivo: em `raw.despesas_ceap` o CNPJ/CPF vem com pontuação `085.324.290/0013-1`, enquanto no CEIS vem apenas com dígitos `07097066423`; padronizar para apenas dígitos mantendo `VARCHAR` preserva os 63.074 zeros à esquerda e viabiliza o JOIN)*
  - `txtNumero` -> `numero_documento` *(Motivo: em faturas de `TELEFONIA` / `CELULAR FUNCIONAL`, `ideDocumento` vale `'0'` e o número real da fatura mora em `txtNumero`; omitir esta coluna num `SELECT DISTINCT` colapsaria 31 faturas reais de mesmo valor mensal)*
  - `indTipoDocumento` -> `tipo_documento_id`
  - `datEmissao` -> `data_emissao`
  - `vlrDocumento` -> `valor_documento`
  - `vlrGlosa` -> `valor_glosa`
  - `vlrLiquido` -> `valor_liquido`
  - `numAno` -> `ano_competencia`
  - `numMes` -> `mes_competencia`
  - `numParcela` -> `parcela`
  - `numLote` -> `lote_id`
  - `nuDeputadoId` -> `cadastro_interno_id`

- **`refined.deputados`**:
  - `split_part(uri, '/', -1)` -> `deputado_id` *(Motivo: a chave que casa com `despesas_ceap.ideCadastro` é o código numérico final da `uri` da API da Câmara)*
  - `nome` -> `nome_parlamentar`
  - `nomeCivil` -> `nome_civil`
  - `idLegislaturaInicial` -> `legislatura_inicial_id`
  - `idLegislaturaFinal` -> `legislatura_final_id`
  - `siglaSexo` -> `sexo`
  - `dataNascimento` -> `data_nascimento`
  - `dataFalecimento` -> `data_falecimento`
  - `ufNascimento` -> `uf_nascimento`
  - `municipioNascimento` -> `municipio_nascimento`

- **`refined.sancoes_ceis`**:
  - `"CÓDIGO DA SANÇÃO"` -> `sancao_id`
  - `"TIPO DE PESSOA"` -> `tipo_pessoa`
  - `regexp_replace("CPF OU CNPJ DO SANCIONADO", '[^0-9]', '', 'g')` -> `documento_sancionado`
  - `"NOME DO SANCIONADO"` -> `nome_sancionado`
  - `"RAZÃO SOCIAL - CADASTRO RECEITA"` -> `razao_social_receita`
  - `"CATEGORIA DA SANÇÃO"` -> `categoria_sancao`
  - `"DATA INÍCIO SANÇÃO"` -> `data_inicio_sancao`
  - `"DATA FINAL SANÇÃO"` -> `data_fim_sancao`
  - `"DATA PUBLICAÇÃO"` -> `data_publicacao`
  - `"ABRAGÊNCIA DA SANÇÃO"` -> `abrangencia_sancao`
  - `"ÓRGÃO SANCIONADOR"` -> `orgao_sancionador`
  - `"UF ÓRGÃO SANCIONADOR"` -> `uf_orgao_sancionador`
  - `"ESFERA ÓRGÃO SANCIONADOR"` -> `esfera_orgao_sancionador`

- **`refined.cotas_uf`**:
  - `codigo_ibge_uf` -> `codigo_ibge`
  - `sigla_uf` -> `uf`
  - `nome_uf` -> `nome_estado`
  - `regiao` -> `regiao`
  - `limite_mensal_cota` -> `limite_mensal_cota`

### 3. TIPOS
- **Datas com hora (`data_emissao`)**: `TIMESTAMP`, formato declarado `'%Y-%m-%dT%H:%M:%S'`. *(Motivo: 27.391 notas fiscais em `despesas_ceap` possuem horário diferente de `00:00:00`)*.
- **Datas sem hora**: `DATE`, formato declarado conforme a fonte:
  - Em `deputados` (`data_nascimento`, `data_falecimento`): `'%Y-%m-%d'`.
  - Em `sancoes_ceis` (`data_inicio_sancao`, `data_fim_sancao`, `data_publicacao`): `'%d/%m/%Y'`.
- **Dinheiro (`valor_documento`, `valor_glosa`, `valor_liquido`, `limite_mensal_cota`)**: `DECIMAL(12,2)`. *(Motivo: `DOUBLE` causa erro de ponto flutuante em somas financeiras)*.
- **Contagens e códigos inteiros (`legislatura_id`, `subcota_id`, `tipo_documento_id`, `ano_competencia`, `mes_competencia`, `parcela`, `lote_id`, `cadastro_interno_id`, `legislatura_inicial_id`, `legislatura_final_id`, `codigo_ibge`)**: `INTEGER`.
- **Identificadores que parecem número (`documento_id`, `deputado_id`, `documento_fornecedor`, `sancao_id`, `documento_sancionado`)**: `VARCHAR`. *(Motivo: ninguém soma CNPJ, CPF ou ID; 63.074 notas em `despesas_ceap` e 6.405 sanções em `sancoes_ceis` começam com zero à esquerda)*.
- As conversões são feitas em SQL pelo DuckDB (`strptime`, `CAST`), disparadas pelo Python.

### 4. CONVERSÃO QUE FALHA
Para tudo. Usa `strptime` e `CAST` (que lançam erro), nunca `try_strptime` ou `TRY_CAST` (que transformam falha em nulo calado). Ao falhar: informa tabela e erro, e encerra com `sys.exit(1)`.
- *Motivo*: um nulo fabricado por falha de conversão se mistura para sempre com os nulos verdadeiros do dado.

### 5. DUPLICATAS
- Linha inteira repetida (`SELECT DISTINCT`): mantém uma e conta quantas saíram.
- Chave primária das tabelas dimensionais/cadastrais:
  - `deputados`: `(deputado_id)`
  - `sancoes_ceis`: `(sancao_id)`
  - `cotas_uf`: `(uf)`
  Se qualquer uma dessas chaves repetir com conteúdo diferente após deduplicação de linha inteira, para tudo e encerra com `sys.exit(1)`.
- Em `despesas_ceap`, um mesmo `documento_id` pode ter múltiplos lançamentos legítimos (ex.: passagens aéreas com trechos/passageiros ou rateio entre subcotas — 171.059 linhas para 163.192 `documento_id`); portanto a deduplicação em `despesas_ceap` remove apenas cópias exatas da linha inteira.

### 6. NULOS
Nenhuma linha é apagada por ter nulo (`dropna` proibido). Nenhum nulo é preenchido com zero ou string fictícia.
- *Motivos apoiados na investigação do banco*:
  - Em `despesas_ceap`, as **7.841** linhas com `data_emissao` nula são 100% despesas de `TELEFONIA` faturadas por competência (`ano_competencia`, `mes_competencia`). Apagá-las eliminaria gastos de telefonia.
  - Em `despesas_ceap`, as **937** linhas sem `deputado_id`, sem `uf` e sem `partido` são gastos institucionais de **Lideranças Partidárias** (`LID.GOV-CD`, `LIDERANÇA DO PT`, etc.).
  - Em `deputados`, os **3.530** nulos em `data_falecimento` são os parlamentares vivos.
  - Em `sancoes_ceis`, os **2.030** nulos em `data_fim_sancao` são sanções por prazo indeterminado.

### 7. SAÍDA NA TELA E TRATAMENTO DE ERRO
- Verifica antes de transformar se as quatro tabelas de entrada existem em `raw`. Faltando qualquer uma, lista quais, orienta a rodar `uv run python -m pipeline.ingestao` e encerra com `sys.exit(1)`.
- Imprime uma linha por tabela com contagem de entrada, saída e duplicatas removidas, seguida dos nulos mantidos por coluna, e total final (`202.714 linhas`).

### CRITÉRIOS DE ACEITE
- Quatro tabelas em `refined`, total de `202.714` linhas (`171.059` + `7.889` + `23.739` + `27`), `0` duplicatas.
- `DESCRIBE refined.despesas_ceap` mostra `TIMESTAMP` em `data_emissao` e `DECIMAL(12,2)` nas três colunas de valor.
- Nulos de `data_emissao` em `refined.despesas_ceap` = `7.841` (igual a `raw`); nulos de `deputado_id`, `uf` e `partido` = `937`.
- `sum(valor_liquido)` em `refined.despesas_ceap` bate centavo por centavo com `sum(CAST(vlrLiquido AS DECIMAL(12,2)))` em `raw` (`R$ 215.086.686,41`).
- `documento_fornecedor` preserva o zero à esquerda (`63.074` registros começando com `'0'`).
