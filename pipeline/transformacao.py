"""Etapa 2 — Transformação de `raw` para `refined` no DuckDB (`auditoria.duckdb`).

SPEC DO MÓDULO (Fonte da Verdade):
1. ESCOPO:
   Lê de `raw` e escreve em `refined` para quatro tabelas:
   - refined.despesas_ceap (171.059 linhas)
   - refined.deputados     (7.889 linhas)
   - refined.sancoes_ceis  (23.739 linhas)
   - refined.cotas_uf      (27 linhas)
   Total esperado: 202.714 linhas. Nunca altera o schema `raw`.
   `raw.sancoes_cnep` fica de fora (documentada em specs/sancoes_cnep.md).

2. NOMES E PADRONIZAÇÃO:
   - Colunas renomeadas para português em snake_case.
   - Em despesas_ceap, `sgUF = 'NA'` vira NULL (`NULLIF(sgUF, 'NA')`), pois representa
     as 937 despesas de Lideranças Partidárias sem UF e sem deputado_id.
   - Documentos (CNPJ/CPF) em despesas_ceap e sancoes_ceis têm pontuação removida via
     `regexp_replace(..., '[^0-9]', '', 'g')`, permanecendo VARCHAR para preservar os
     zeros à esquerda (63.074 em despesas_ceap e 6.405 em sancoes_ceis).
   - Em deputados, `deputado_id` é extraído do sufixo da `uri` (`split_part(uri, '/', -1)`).

3. TIPOS E FALHA DE CONVERSÃO:
   - `data_emissao` -> TIMESTAMP com formato declarado '%Y-%m-%dT%H:%M:%S'.
   - Datas em deputados -> DATE com formato declarado '%Y-%m-%d'.
   - Datas em sancoes_ceis -> DATE com formato declarado '%d/%m/%Y'.
   - Valores monetários -> DECIMAL(12,2) (nunca DOUBLE).
   - Proibido usar try_strptime ou TRY_CAST: qualquer valor que falhe na conversão
     interrompe a execução com mensagem clara e sys.exit(1).

4. DUPLICATAS E NULOS:
   - Remove apenas duplicatas exatas da linha inteira (SELECT DISTINCT) e verifica
     unicidade da chave nas tabelas cadastrais; conflito de chave encerra com sys.exit(1).
   - Nenhuma linha é descartada por conter NULL e nenhum NULL é preenchido (nulos em
     data_emissao são faturas de telefonia; nulos em deputado_id são lideranças;
     nulos em data_falecimento são deputados vivos; nulos em data_fim_sancao são
     sanções por prazo indeterminado).
"""

import sys
import duckdb
from pipeline import db

TABELAS_ENTRADA: tuple[str, ...] = (
    "despesas_ceap",
    "deputados",
    "sancoes_ceis",
    "cotas_uf",
)

# SQLs de transformação com formatos declarados explicitamente (sem TRY_CAST / try_strptime)
SQL_TRANSFORMACAO: dict[str, str] = {
    "despesas_ceap": """
        SELECT DISTINCT
            ideDocumento AS documento_id,
            txNomeParlamentar AS nome_parlamentar,
            ideCadastro AS deputado_id,
            NULLIF(sgUF, 'NA') AS uf,
            sgPartido AS partido,
            CAST(codLegislatura AS INTEGER) AS legislatura_id,
            CAST(numSubCota AS INTEGER) AS subcota_id,
            txtDescricao AS categoria_despesa,
            txtFornecedor AS nome_fornecedor,
            regexp_replace(txtCNPJCPF, '[^0-9]', '', 'g') AS documento_fornecedor,
            txtNumero AS numero_documento,
            CAST(indTipoDocumento AS INTEGER) AS tipo_documento_id,
            CASE
                WHEN datEmissao IS NOT NULL
                THEN strptime(datEmissao, '%Y-%m-%dT%H:%M:%S')
                ELSE NULL
            END AS data_emissao,
            CAST(vlrDocumento AS DECIMAL(12,2)) AS valor_documento,
            CAST(vlrGlosa AS DECIMAL(12,2)) AS valor_glosa,
            CAST(vlrLiquido AS DECIMAL(12,2)) AS valor_liquido,
            CAST(numAno AS INTEGER) AS ano_competencia,
            CAST(numMes AS INTEGER) AS mes_competencia,
            CAST(numParcela AS INTEGER) AS parcela,
            CAST(numLote AS INTEGER) AS lote_id,
            CAST(nuDeputadoId AS INTEGER) AS cadastro_interno_id
        FROM raw.despesas_ceap
    """,
    "deputados": """
        SELECT DISTINCT
            split_part(uri, '/', -1) AS deputado_id,
            nome AS nome_parlamentar,
            nomeCivil AS nome_civil,
            CAST(idLegislaturaInicial AS INTEGER) AS legislatura_inicial_id,
            CAST(idLegislaturaFinal AS INTEGER) AS legislatura_final_id,
            siglaSexo AS sexo,
            CASE
                WHEN dataNascimento IS NOT NULL
                THEN strptime(dataNascimento, '%Y-%m-%d')::DATE
                ELSE NULL
            END AS data_nascimento,
            CASE
                WHEN dataFalecimento IS NOT NULL
                THEN strptime(dataFalecimento, '%Y-%m-%d')::DATE
                ELSE NULL
            END AS data_falecimento,
            ufNascimento AS uf_nascimento,
            municipioNascimento AS municipio_nascimento
        FROM raw.deputados
    """,
    "sancoes_ceis": """
        SELECT DISTINCT
            "CÓDIGO DA SANÇÃO" AS sancao_id,
            "TIPO DE PESSOA" AS tipo_pessoa,
            regexp_replace("CPF OU CNPJ DO SANCIONADO", '[^0-9]', '', 'g') AS documento_sancionado,
            "NOME DO SANCIONADO" AS nome_sancionado,
            "RAZÃO SOCIAL - CADASTRO RECEITA" AS razao_social_receita,
            "CATEGORIA DA SANÇÃO" AS categoria_sancao,
            CASE
                WHEN "DATA INÍCIO SANÇÃO" IS NOT NULL
                THEN strptime("DATA INÍCIO SANÇÃO", '%d/%m/%Y')::DATE
                ELSE NULL
            END AS data_inicio_sancao,
            CASE
                WHEN "DATA FINAL SANÇÃO" IS NOT NULL
                THEN strptime("DATA FINAL SANÇÃO", '%d/%m/%Y')::DATE
                ELSE NULL
            END AS data_fim_sancao,
            CASE
                WHEN "DATA PUBLICAÇÃO" IS NOT NULL
                THEN strptime("DATA PUBLICAÇÃO", '%d/%m/%Y')::DATE
                ELSE NULL
            END AS data_publicacao,
            "ABRAGÊNCIA DA SANÇÃO" AS abrangencia_sancao,
            "ÓRGÃO SANCIONADOR" AS orgao_sancionador,
            "UF ÓRGÃO SANCIONADOR" AS uf_orgao_sancionador,
            "ESFERA ÓRGÃO SANCIONADOR" AS esfera_orgao_sancionador
        FROM raw.sancoes_ceis
    """,
    "cotas_uf": """
        SELECT DISTINCT
            CAST(codigo_ibge_uf AS INTEGER) AS codigo_ibge,
            sigla_uf AS uf,
            nome_uf AS nome_estado,
            regiao AS regiao,
            CAST(limite_mensal_cota AS DECIMAL(12,2)) AS limite_mensal_cota
        FROM raw.cotas_uf
    """,
}

CHAVES_UNICAS: dict[str, str] = {
    "deputados": "deputado_id",
    "sancoes_ceis": "sancao_id",
    "cotas_uf": "uf",
}


def formatar_milhar(valor: int) -> str:
    return f"{valor:,}".replace(",", ".")


def verificar_tabelas_raw(con: duckdb.DuckDBPyConnection) -> None:
    """Garante que todas as tabelas de entrada existem no schema raw."""
    existentes = {
        row[0]
        for row in con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'raw'"
        ).fetchall()
    }
    faltantes = [t for t in TABELAS_ENTRADA if t not in existentes]
    if faltantes:
        print(
            "Erro: tabelas obrigatórias não encontradas no schema raw: "
            + ", ".join(f"raw.{t}" for t in faltantes)
            + ". Rode 'uv run python -m pipeline.ingestao' antes da transformação.",
            file=sys.stderr,
        )
        sys.exit(1)


def contar_nulos_por_coluna(
    con: duckdb.DuckDBPyConnection, schema: str, tabela: str, total_linhas: int
) -> list[tuple[str, int]]:
    """Devolve lista de (coluna, qtd_nulos) apenas para colunas que possuem ao menos 1 nulo."""
    if total_linhas == 0:
        return []
    colunas = [
        row[0]
        for row in con.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = ? AND table_name = ? ORDER BY ordinal_position",
            [schema, tabela],
        ).fetchall()
    ]
    expressoes = ", ".join(f'count(*) - count("{c}")' for c in colunas)
    contagens = con.execute(f"SELECT {expressoes} FROM {schema}.{tabela}").fetchall()[0]
    return [(col, int(qtd)) for col, qtd in zip(colunas, contagens) if int(qtd) > 0]


def verificar_conflito_chave(
    con: duckdb.DuckDBPyConnection, tabela: str, coluna_chave: str
) -> None:
    """Encerra com sys.exit(1) se houver chave repetida com conteúdo diferente."""
    conflitos = con.execute(
        f"SELECT {coluna_chave}, count(*) AS n "
        f"FROM refined.{tabela} "
        f"GROUP BY {coluna_chave} HAVING count(*) > 1 LIMIT 5"
    ).fetchall()
    if conflitos:
        chaves_str = ", ".join(f"{r[0]!r} ({r[1]}x)" for r in conflitos)
        print(
            f"Erro: chave primária '{coluna_chave}' repetida com conteúdos distintos "
            f"em refined.{tabela}: {chaves_str}",
            file=sys.stderr,
        )
        sys.exit(1)


def executar_transformacao() -> int:
    """Executa a transformação de raw para refined e devolve o total de linhas gravadas."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    con = db.conectar()
    try:
        verificar_tabelas_raw(con)
        db.criar_schema(con, "refined")

        total_refined = 0
        for tabela in TABELAS_ENTRADA:
            linhas_entrada = int(
                con.execute(f"SELECT count(*) FROM raw.{tabela}").fetchall()[0][0]
            )
            sql = SQL_TRANSFORMACAO[tabela]
            try:
                con.execute(f"CREATE OR REPLACE TABLE refined.{tabela} AS {sql}")
            except duckdb.Error as exc:
                print(
                    f"Erro na conversão de tipos ao transformar raw.{tabela} -> refined.{tabela}: {exc}",
                    file=sys.stderr,
                )
                sys.exit(1)

            linhas_saida = int(
                con.execute(f"SELECT count(*) FROM refined.{tabela}").fetchall()[0][0]
            )
            if tabela in CHAVES_UNICAS:
                verificar_conflito_chave(con, tabela, CHAVES_UNICAS[tabela])

            duplicatas = linhas_entrada - linhas_saida
            total_refined += linhas_saida

            nome_qual = f"refined.{tabela}"
            print(
                f"✓ {nome_qual:<24} {formatar_milhar(linhas_entrada):>9} → "
                f"{formatar_milhar(linhas_saida):>9} linhas  ({formatar_milhar(duplicatas)} duplicatas)"
            )

            nulos = contar_nulos_por_coluna(con, "refined", tabela, linhas_saida)
            if nulos:
                resumo_nulos = ", ".join(
                    f"{col} {formatar_milhar(qtd)}" for col, qtd in nulos
                )
                print(f"    nulos mantidos: {resumo_nulos}")

        print(f"  {'total':<24} {formatar_milhar(total_refined):>21} linhas")
        return total_refined
    finally:
        con.close()


if __name__ == "__main__":
    executar_transformacao()
