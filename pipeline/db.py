"""Módulo de conexão e gravação no banco DuckDB (`auditoria.duckdb`).

SPEC DO MÓDULO (Fonte da Verdade):
1. Expõe exatamente:
   - PASTA_RAW: Path da pasta raw/ resolvido a partir da localização deste arquivo.
   - conectar(): abre o auditoria.duckdb na raiz do projeto, criando se faltar.
   - criar_schema(con, nome): executa CREATE SCHEMA IF NOT EXISTS.
   - gravar(con, df, schema, tabela): recria a tabela (CREATE OR REPLACE TABLE)
     sem alterar tipos ou valores do DataFrame e devolve SELECT count(*) lido do banco.

2. MOTIVOS DAS DECISÕES:
   - Caminhos relativos ao próprio db.py evitam criar um banco vazio no diretório
     corrente quando o comando é disparado de outra pasta.
   - Nenhuma regra de negócio, leitura de CSV ou conversão de tipo mora aqui,
     pois todas as etapas do pipeline importam este módulo.
   - A contagem retornada por gravar() vem de um SELECT count(*) no banco após a
     escrita, provando o que foi efetivamente persistido em disco.
   - A view temporária do DataFrame é desregistrada logo após a gravação para
     não deixar objetos temporários no catálogo.
"""

import re
from pathlib import Path

import duckdb
import pandas as pd

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
PASTA_RAW = RAIZ_PROJETO / "raw"
CAMINHO_BANCO = RAIZ_PROJETO / "auditoria.duckdb"

_IDENTIFICADOR_VALIDO = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validar_identificador(nome: str) -> str:
    if not _IDENTIFICADOR_VALIDO.match(nome):
        raise ValueError(f"Identificador SQL inválido: {nome!r}")
    return nome


def conectar() -> duckdb.DuckDBPyConnection:
    """Abre e devolve uma conexão com o arquivo auditoria.duckdb na raiz do projeto."""
    return duckdb.connect(str(CAMINHO_BANCO))


def criar_schema(con: duckdb.DuckDBPyConnection, nome: str) -> None:
    """Cria o schema caso ainda não exista."""
    schema_seguro = _validar_identificador(nome)
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {schema_seguro}")


def gravar(
    con: duckdb.DuckDBPyConnection,
    df: pd.DataFrame,
    schema: str,
    tabela: str,
) -> int:
    """Grava o DataFrame em schema.tabela (CREATE OR REPLACE) e devolve a contagem do banco."""
    schema_seguro = _validar_identificador(schema)
    tabela_segura = _validar_identificador(tabela)
    criar_schema(con, schema_seguro)

    view_temp = f"_tmp_df_{schema_seguro}_{tabela_segura}"
    con.register(view_temp, df)
    try:
        # DuckDB no pandas 3+ cria colunas string como VARCHAR preservando NULLs
        colunas_cast = ", ".join(
            f'CAST("{col}" AS VARCHAR) AS "{col}"' if str(df[col].dtype) in ("str", "object", "string") else f'"{col}"'
            for col in df.columns
        )
        con.execute(
            f"CREATE OR REPLACE TABLE {schema_seguro}.{tabela_segura} AS "
            f"SELECT {colunas_cast} FROM {view_temp}"
        )
    finally:
        con.unregister(view_temp)

    linhas = con.execute(
        f"SELECT count(*) FROM {schema_seguro}.{tabela_segura}"
    ).fetchall()
    return int(linhas[0][0]) if linhas else 0
