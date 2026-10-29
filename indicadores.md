# Indicadores de Auditoria Cidadã e Compliance (Desafio da Aula 1)

Leitura exploratória das cinco tabelas do schema `raw` (`despesas_ceap`, `deputados`, `sancoes_ceis`, `sancoes_cnep` e `cotas_uf`) para mapear quais perguntas de negócio e de controle social os dados sustentam — e quais não sustentam.

---

## 1. Os 10 Indicadores Sustentados pelo Dado

1. **Execução mensal da Cota Parlamentar e sazonalidade** — `despesas_ceap (numAno, numMes, vlrLiquido, ideDocumento)` — mede o volume financeiro líquido desembolsado mês a mês e identifica picos de execução orçamentária.
2. **Despesa líquida e taxa de glosa por categoria de gasto** — `despesas_ceap (txtDescricao, vlrDocumento, vlrGlosa, vlrLiquido)` — identifica quais rubricas (divulgação, locação de veículos, passagens aéreas, combustível) consomem mais recursos e onde a auditoria interna da Câmara mais rejeita valores (`vlrGlosa`).
3. **Pagamentos a fornecedores sancionados no CEIS (vigentes vs. históricos) `?`** — `despesas_ceap (txtCNPJCPF, datEmissao, vlrLiquido)` + `sancoes_ceis (CPF OU CNPJ DO SANCIONADO, DATA INÍCIO SANÇÃO, DATA FINAL SANÇÃO)` — mede quanto dinheiro público foi pago a empresas listadas no Cadastro de Empresas Inidôneas e Suspensas, separando notas emitidas *durante* a vigência da sanção de notas emitidas fora do período sancionado. *(Depende de padronizar pontuação de CNPJ/CPF e converter datas na Etapa 2).*
4. **Concentração de Pareto de fornecedores (Curva ABC)** — `despesas_ceap (txtCNPJCPF, txtFornecedor, vlrLiquido)` — calcula que fração dos fornecedores concentra 80% de todo o dinheiro da Cota Parlamentar e expõe variações de razão social sob o mesmo CNPJ.
5. **Gasto médio por parlamentar vs. Limite Mensal Oficial da UF** — `despesas_ceap (ideCadastro, sgUF, numMes, vlrLiquido)` + `cotas_uf (sigla_uf, regiao, limite_mensal_cota)` — compara o gasto médio mensal dos deputados de cada estado contra o teto legal da respectiva UF fixado pela Câmara.
6. **Gasto por partido político e despesas de Lideranças Partidárias `?`** — `despesas_ceap (sgPartido, ideCadastro, txNomeParlamentar, vlrLiquido)` — separa os gastos individuais dos deputados (`ideCadastro IS NOT NULL`) dos gastos institucionais das Lideranças de Partido (`ideCadastro IS NULL`, onde `sgUF` vem preenchido como `'NA'`).
7. **Perfil demográfico e geracional de gastos dos deputados** — `despesas_ceap (ideCadastro, vlrLiquido)` + `deputados (uri, siglaSexo, dataNascimento, ufNascimento)` — cruza o gasto parlamentar com os dados cadastrais do deputado através do identificador extraído da `uri` (`split_part(uri, '/', -1) = ideCadastro`).
8. **Pagamentos a fornecedores com sanção ativa por categoria de despesa** — `despesas_ceap (txtDescricao, txtCNPJCPF, datEmissao, vlrLiquido)` + `sancoes_ceis (CPF OU CNPJ DO SANCIONADO, CATEGORIA DA SANÇÃO, DATA INÍCIO SANÇÃO, DATA FINAL SANÇÃO)` — revela em quais tipos de serviço (telefonia, passagens, locação, postos) ocorrem os pagamentos a CNPJs sancionados.
9. **Auditoria de restituições e bilhetes aéreos cancelados (`vlrLiquido <= 0`) `?`** — `despesas_ceap (indTipoDocumento, vlrDocumento, vlrGlosa, vlrRestituicao, vlrLiquido)` — dimensiona os lançamentos de estorno/compensação de passagens aéreas e restituições aos cofres públicos.
10. **Panorama nacional do CEIS por esfera e UF do órgão sancionador** — `sancoes_ceis (CPF OU CNPJ DO SANCIONADO, CÓDIGO DA SANÇÃO, ESFERA ÓRGÃO SANCIONADOR, UF ÓRGÃO SANCIONADOR)` + `cotas_uf (sigla_uf, regiao)` — mede a distribuição geográfica e federativa das sanções administrativas no país e a reincidência (múltiplas sanções para o mesmo CNPJ).

---

## 2. A Pilha do "Não Dá": O Que o Dado Não Sustenta (e Por Quê)

| Indicador desejado | Por que o dado não sustenta |
| :--- | :--- |
| **Superfaturamento de preço unitário (ex.: preço do litro de combustível ou da resma de papel)** | `raw.despesas_ceap` traz apenas o valor total da nota fiscal (`vlrDocumento`, `vlrLiquido`) e a categoria (`txtDescricao`), mas não possui tabela de itens da nota fiscal com quantidade unitária e preço por item. |
| **Patrimônio pessoal ou evolução patrimonial do deputado** | `raw.deputados` contém apenas dados civis e biográficos (nascimento, sexo, município de origem, legislaturas). Dados de declaração de bens ficam no TSE (DivulgaCandContas), fora deste escopo. |
| **Quadro societário (QSA) para detectar parentesco entre deputado e dono da empresa** | Tanto `despesas_ceap` quanto `sancoes_ceis` identificam o fornecedor pelo CNPJ/razão social, mas não contêm a tabela de sócios da Receita Federal. |
| **Motivo detalhado de cada glosa administrativa** | Sabemos exatamente quanto foi glosado (`vlrGlosa > 0` em 9.873 notas, somando R$ 1.012.889,88), mas não há coluna descrevendo a justificativa do fiscal da Câmara para o corte. |
