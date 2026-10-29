# Spec da Etapa 6 — Vários anos, mandatos oficiais e atualização automática

## CONTEXTO
O pipeline nasceu com a CEAP 2025 congelada em `raw/`. Esta etapa faz o painel acompanhar o ano corrente sem perder os anteriores, troca a aproximação de "meses de exercício" pelos períodos oficiais de mandato e permite republicar o GitHub Pages com dados novos por um workflow sob demanda. As specs das etapas 1 a 5 continuam valendo; onde esta spec muda uma regra delas, vale esta.

## 1. FONTES (`scripts/baixar_dados_oficiais.py` → `raw/`)
| Arquivo | Origem | Regra |
| :--- | :--- | :--- |
| `despesas_ceap.csv.gz` | `camara.leg.br/cotas/Ano-AAAA.csv.zip`, de 2025 até o ano corrente | Arquivos anuais empilhados sem alteração; se as colunas divergirem entre anos, o download falha. `numAno` identifica o ano. |
| `sancoes_ceis.csv.gz`, `sancoes_cnep.csv.gz` | Portal da Transparência (CGU) | A CGU só mantém o arquivo do dia: tenta a data de hoje no fuso de Brasília e, se der erro HTTP, a de ontem. Nunca data fixa no código. |
| `cotas_uf.csv.gz` | API de Localidades do IBGE | Só o cadastro da UF (`codigo_ibge_uf`, `sigla_uf`, `nome_uf`, `regiao`). O limite da cota saiu daqui. |
| `limites_cota_uf.csv.gz` **(novo)** | Atos da Mesa, digitados no script | Uma linha por UF e início de vigência: `2023-02-01` (Ato n. 270/2023) e `2026-02-20` (Ato n. 244/2026, IPCA de fev/2023 a dez/2025, fator 1,1375, valores conferidos na página "Cota Parlamentar" da Câmara). |
| `historico_deputados.csv.gz` **(novo)** | `dadosabertos.camara.leg.br/api/v2/deputados/{id}/historico` | Todos os eventos de mandato de cada deputado com despesa na CEAP, sem alteração. Qualquer falha após 3 tentativas derruba o download inteiro (nunca grava um histórico pela metade). |

## 2. INGESTÃO E TRANSFORMAÇÃO
- A ingestão passa a exigir sete arquivos; as proibições da etapa 1 continuam (tudo `VARCHAR`, nada corrigido).
- `refined.cotas_uf` perde `limite_mensal_cota`.
- `refined.limites_cota_uf`: `uf`, `vigencia_inicio` (`DATE`, formato `'%Y-%m-%d'`), `limite_mensal_cota` (`DECIMAL(12,2)`), `ato_da_mesa`. Chave única: `(uf, vigencia_inicio)`.
- `refined.historico_deputados`: `deputado_id`, `data_hora` (`TIMESTAMP`, formato `'%Y-%m-%dT%H:%M'`), `situacao`, `condicao_eleitoral`, `descricao_status`, `partido`, `uf`, `legislatura_id` (`INTEGER`), `nome_parlamentar`. Grão: um evento. Sem chave única (a API repete o mesmo instante em legislaturas diferentes); só `SELECT DISTINCT`.
- As contagens dos critérios de aceite das etapas 1 e 2 valem para o retrato de 2025; com vários anos e o CEIS do dia, elas mudam a cada download.

## 3. TETO DA COTA (`sql/marts/00_teto_deputado_ano.sql` → `marts.teto_deputado_ano`)
Grão: um deputado em um ano `(ano, deputado_id)`, só deputados com lançamento válido no ano. É o único lugar onde o teto é calculado; os marts `04`, `06`, `10` e `11` leem dele.
- **Dias de efetivo exercício** (art. 11 e 12 do Ato n. 43/2009): um evento cuja `descricao_status` **contém** `'Entrada - '` abre exercício; um evento que contém `'Saída - '` fecha, contando o próprio dia do afastamento. Exceção: `'Licença para Tratamento de Saúde'` não fecha (art. 11, § 2º: a cota não é reduzida). Eventos `DIVERSO`, troca de partido ou de nome não mudam o estado.
  - *Motivo do "contém"*: a API registra reentradas como `"Entrada - Reassunção / DIVERSO - ..."` e `"DIVERSO - ... Efetivação ... / Entrada - Reassunção"`, às vezes com `situacao = 'CONVOCADO'`. Usar `situacao = 'Exercício'` ou "começa com" deixava suplentes com 43 dias de exercício num ano em que gastaram todos os meses.
- **Teto do período** = soma, em cada dia de exercício do ano até o corte, de `limite_mensal_cota vigente no dia ÷ número de dias do mês`. A mesma fórmula cobre a proporcionalidade do art. 11 e a troca de limite no meio de fevereiro de 2026.
- **Corte do ano**: último dia do último mês de competência com dados naquele ano. Num ano em curso, o teto vai até esse dia.
- **Reserva**: deputado sem nenhum dia oficial de exercício no ano usa a aproximação da etapa anterior (do primeiro dia do primeiro mês com despesa ao último dia do último mês), marcado em `fonte_periodo = 'aproximado'`; os demais ficam `'oficial'`.
- **UF e partido do ano**: UF de representação na CEAP; partido = o do lançamento mais recente no ano (quem trocou de partido na janela partidária conta inteiro no partido novo).
- Colunas: `ano`, `deputado_id`, `uf`, `partido`, `despesa_liquida`, `dias_exercicio`, `meses_exercicio` (soma de dias ÷ dias do mês, 2 casas), `teto_periodo` (2 casas), `pct_teto_utilizado` (2 casas), `fonte_periodo`.

## 4. TODOS OS MARTS GANHAM `ano`
- `ano` (= `ano_competencia`) entra no grão de todos os marts `01` a `12`; rankings, percentuais e acumulados (`rank()`, `pct_total`, Pareto) são calculados dentro de cada ano (`PARTITION BY ano`).
- A vigência de sanção no CEIS continua avaliada pela data de cada nota; só o agrupamento passa a ser por ano.
- `marts.gasto_medio_por_uf.limite_mensal_cota` passa a ser o limite vigente no corte do ano.

## 5. QUALIDADE
Todas as regras que comparavam marts de uma linha passam a comparar ano a ano (junção por `ano`), exigindo também o mesmo conjunto de anos dos dois lados. Regras novas:
- **Dentro do domínio**: todo `(ano, deputado_id)` de `marts.teto_deputado_ano` tem `teto_periodo > 0` (um limite foi encontrado para cada dia; um ano sem tabela de limites derruba o pipeline em vez de mostrar 0%).
- **Nada some sem aviso**: pelo menos 95% dos deputados de cada ano com `fonte_periodo = 'oficial'` (se a API da Câmara falhar em massa, o pipeline para).

## 6. PAINEL E RELATÓRIO
- `painel.anos(dados)` lista os anos (mais recente primeiro) e `painel.do_ano(dados, ano)` filtra cada mart pela coluna `ano` (só filtro, nenhum cálculo).
- `painel.periodo(dados_ano)` devolve o primeiro e o último mês com dados e se o ano está **parcial**: último mês antes de dezembro ou menos de 90 dias desde 31/12 do ano (art. 4º, § 12, do Ato n. 43/2009: a nota pode ser apresentada até 90 dias depois da despesa). No ano parcial, o painel mostra um aviso de que os meses recentes ainda vão crescer.
- Streamlit: seletor de ano no cabeçalho, abrindo no mais recente.
- Relatório: `relatorio.html` mostra o ano mais recente e `relatorio_AAAA.html` cada ano anterior; todas as páginas têm links entre os anos. Cada página continua abaixo de 200 KB.

## 7. ATUALIZAÇÃO AUTOMÁTICA (`.github/workflows/atualizar_dados.yml`)
- Só sob demanda (`workflow_dispatch`), na `main`. O agendamento semanal (segunda, 12h UTC) fica comentado no arquivo: o projeto é uma demonstração e não deve gerar commits sozinho.
- Passos: `uv sync` → `scripts/baixar_dados_oficiais.py` → `pytest` → `executar.py` (pipeline do zero + qualidade + relatórios). Qualquer falha encerra o job e a página anterior continua no ar.
- Commit direto na `main` **apenas dos `relatorio*.html`**, e só se mudaram.
  - *Motivo de não commitar `raw/`*: os arquivos brutos somam ~14 MB e mudam toda semana (CEAP do ano corrente e CEIS do dia); versioná-los semanalmente faria o repositório crescer centenas de MB por ano. O retrato em `raw/` continua servindo para rodar o projeto offline e é atualizado à mão quando for útil.

## 8. DIVULGAÇÃO NO PERÍODO ELEITORAL (`sql/marts/13_divulgacao_eleitoral.sql` → `marts.divulgacao_eleitoral`)
- Grão: um mês de competência `(ano, mes)`, com `despesa_divulgacao` (categorias que começam com "DIVULGA"), `despesa_demais` e `deputados_divulgacao`.
- Regra testada: o art. 2º, XII, do Ato da Mesa n. 43/2009 só deixa a cota pagar divulgação da atividade parlamentar **fora** dos 120 dias anteriores às eleições federais, estaduais ou municipais, salvo para quem não é candidato.
- `data_eleicao`: primeiro domingo de outubro dos anos pares (Constituição, arts. 28, 29 e 77), calculada no SQL; `NULL` em anos ímpares. `inicio_vedacao = data_eleicao - 120 dias`.
  - *Motivo de calcular, não digitar*: a regra constitucional vale para qualquer ano futuro sem manutenção.
- **Qualidade**: `despesa_divulgacao + despesa_demais` bate com `marts.gastos_mensais.despesa_liquida` em todos os meses.
