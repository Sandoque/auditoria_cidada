# Spec de Investigação — `raw.sancoes_cnep` (Desafio de Especificação da Etapa 2)

Assim como na metodologia do curso, `raw.sancoes_cnep` (Cadastro Nacional de Empresas Punidas — Lei Anticorrupção n.º 12.846/2013) ficou fora da transformação principal e teve sua spec escrita após investigação completa no banco via SQL em somente leitura.

## 1. ESCOPO
- Origem: `raw.sancoes_cnep` (1.853 linhas, 25 colunas `VARCHAR`).
- Destino futuro caso integrada: `refined.sancoes_cnep` (mantendo o grão de sanção individual) e `marts.cnep_por_fornecedor` (quando reduzida a 1 linha por CNPJ).

## 2. DESCOBERTAS DA INVESTIGAÇÃO NO BANCO (MOTIVOS COM NÚMEROS)

1. **Grão e Multiplicação no JOIN ($1:N$)**:
   - A tabela tem **1.853 linhas** e **1.853 `"CÓDIGO DA SANÇÃO"` distintos** (`sancao_id` é PK), mas apenas **1.058 CPF/CNPJs distintos** (`documento_sancionado`).
   - Há empresas com até **34 sanções** no CNEP. Um `JOIN` direto entre `despesas_ceap` e `sancoes_cnep` pelo CNPJ sem ajustar o grão antes multiplica o valor das notas fiscais pelo número de punições da empresa.
2. **Armadilha de Formato Monetário Brasileiro (`VALOR DA MULTA`)**:
   - Diferente da Câmara dos Deputados (que usa ponto decimal `1467.00`), a CGU exporta `"VALOR DA MULTA"` no CNEP com **vírgula decimal** (ex.: `'45000,00'`, `'1054321,89'`).
   - Um `CAST("VALOR DA MULTA" AS DECIMAL(14,2))` direto falha na primeira linha; usar `TRY_CAST` transformaria todas as multas com centavos em `NULL` silenciosamente. A regra obrigatória antes do `CAST` é `replace("VALOR DA MULTA", ',', '.')::DECIMAL(14,2)`.
3. **Zeros à Esquerda no CNPJ/CPF**:
   - **489 linhas** (26,4% da tabela) têm `"CPF OU CNPJ DO SANCIONADO"` começando com `'0'`. Deve permanecer `VARCHAR`, normalizado com `regexp_replace("CPF OU CNPJ DO SANCIONADO", '[^0-9]', '', 'g')`.
4. **Nulos que são Informação**:
   - `"DATA FINAL SANÇÃO"` é nula em **1.810 das 1.853 linhas** (97,7%), pois a maioria das sanções do CNEP consiste em **Multa da Lei Anticorrupção** ou **Reparação de Danos**, que não possuem prazo de vigência temporal como a suspensão de licitar, mas sim obrigação pecuniária. Apagar linhas sem `"DATA FINAL SANÇÃO"` apagaria quase todo o cadastro.

## 3. REGRAS DE TRANSFORMAÇÃO E AVISO A QUEM CONSOME
- **Duplicatas**: 0 linhas inteiras repetidas (`1.853 -> 1.853`).
- **Datas**: `"DATA INÍCIO SANÇÃO"` e `"DATA FINAL SANÇÃO"` convertidas para `DATE` com `strptime(..., '%d/%m/%Y')::DATE` (0 falhas nas linhas preenchidas).
- **Aviso a quem consome**: Nunca faça `JOIN` direto de `sancoes_cnep` com `despesas_ceap` pelo `documento_sancionado` para somar despesas; agrupe antes por `documento_sancionado` numa CTE.
