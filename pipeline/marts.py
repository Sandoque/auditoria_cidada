"""Etapa 3 — Executor transacional dos marts SQL (`sql/marts/*.sql` -> schema `marts`).

SPEC DO MÓDULO (Fonte da Verdade):
1. ESCOPO:
   Lê de `refined` e grava no schema `marts`. Apaga e recria o schema `marts`
   (`DROP SCHEMA IF EXISTS marts CASCADE`) a cada execução para que arquivos
   removidos de `sql/marts/` não sobrevivam no banco.

2. UM ARQUIVO, UMA TABELA:
   Lê `sql/marts/*.sql` em ordem alfabética. O nome da tabela é o nome do arquivo
   sem o prefixo numérico `NN_` e sem `.sql` (ex.: `01_gastos_mensais.sql` ->
   `marts.gastos_mensais`). O Python apenas tira espaços e `;` do fim.

3. ERRO E TRANSAÇÃO ÚNICA:
   - Verifica se as seis tabelas de `refined` existem antes de começar.
   - Valida que todos os arquivos seguem o padrão `NN_nome.sql` e que não há nomes
     de tabela repetidos antes de tocar no schema `marts`.
   - Executa `DROP SCHEMA`, `CREATE SCHEMA` e todos os `CREATE TABLE` dentro de uma
     única transação: se qualquer SQL falhar ou produzir 0 linhas, faz `ROLLBACK` e
     encerra com `sys.exit(1)`, preservando o estado anterior do schema `marts`.
"""

import logging
import re
import sys
from pathlib import Path

import duckdb

from pipeline import db

logger = logging.getLogger(__name__)

PASTA_MARTS = db.RAIZ_PROJETO / "sql" / "marts"
TABELAS_REFINED_OBRIGATORIAS: tuple[str, ...] = (
    "despesas_ceap",
    "deputados",
    "sancoes_ceis",
    "cotas_uf",
    "limites_cota_uf",
    "historico_deputados",
)
PADRAO_ARQUIVO = re.compile(r"^\d{2}_([A-Za-z_][A-Za-z0-9_]*)\.sql$")


def formatar_milhar(valor: int) -> str:
    return f"{valor:,}".replace(",", ".")


def verificar_tabelas_refined(con: duckdb.DuckDBPyConnection) -> None:
    existentes = {
        row[0]
        for row in con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'refined'"
        ).fetchall()
    }
    faltantes = [t for t in TABELAS_REFINED_OBRIGATORIAS if t not in existentes]
    if faltantes:
        logger.error(
            "Erro: tabelas obrigatórias ausentes no schema refined: %s. "
            "Rode 'uv run python -m pipeline.transformacao' antes dos marts.",
            ", ".join(f"refined.{t}" for t in faltantes),
        )
        sys.exit(1)


def listar_e_validar_arquivos(pasta: Path) -> list[tuple[Path, str]]:
    if not pasta.is_dir():
        logger.error("Erro: pasta de marts não encontrada: %s", pasta)
        sys.exit(1)

    arquivos = sorted(pasta.glob("*.sql"))
    if not arquivos:
        logger.error("Erro: nenhum arquivo .sql encontrado em %s", pasta)
        sys.exit(1)

    invalidos: list[str] = []
    mapa_nomes: dict[str, list[str]] = {}
    plano: list[tuple[Path, str]] = []

    for arq in arquivos:
        m = PADRAO_ARQUIVO.match(arq.name)
        if not m:
            invalidos.append(arq.name)
            continue
        nome_tabela = m.group(1)
        mapa_nomes.setdefault(nome_tabela, []).append(arq.name)
        plano.append((arq, nome_tabela))

    duplicados = {k: v for k, v in mapa_nomes.items() if len(v) > 1}
    if invalidos or duplicados:
        if invalidos:
            logger.error(
                "Erro: arquivos sem o prefixo obrigatório NN_nome.sql: %s",
                ", ".join(invalidos),
            )
        if duplicados:
            for nome_tab, arqs in duplicados.items():
                logger.error(
                    "Erro: múltiplos arquivos geram a mesma tabela marts.%s: %s",
                    nome_tab,
                    ", ".join(arqs),
                )
        sys.exit(1)

    return plano


def executar_marts() -> int:
    """Executa todos os arquivos sql/marts/*.sql e devolve a soma de linhas dos marts."""
    db.configurar_logging()

    plano = listar_e_validar_arquivos(PASTA_MARTS)

    con = db.conectar()
    try:
        verificar_tabelas_refined(con)

        resultados: list[tuple[str, int]] = []
        con.execute("BEGIN TRANSACTION")
        try:
            con.execute("DROP SCHEMA IF EXISTS marts CASCADE")
            con.execute("CREATE SCHEMA marts")

            for caminho_sql, nome_tabela in plano:
                conteudo = caminho_sql.read_text(encoding="utf-8").strip()
                if conteudo.endswith(";"):
                    conteudo = conteudo[:-1].strip()

                if not conteudo:
                    raise ValueError("arquivo SQL vazio")

                con.execute(f"CREATE TABLE marts.{nome_tabela} AS {conteudo}")
                contagem = int(
                    con.execute(f"SELECT count(*) FROM marts.{nome_tabela}").fetchall()[0][0]
                )
                if contagem == 0:
                    raise RuntimeError(
                        f"o mart marts.{nome_tabela} ({caminho_sql.name}) voltou com 0 linhas"
                    )
                resultados.append((nome_tabela, contagem))

            con.execute("COMMIT")
        except (duckdb.Error, RuntimeError, ValueError, OSError) as exc:
            con.execute("ROLLBACK")
            nome_arq = caminho_sql.name if "caminho_sql" in locals() else "<desconhecido>"
            logger.error("Erro ao executar %s: %s", nome_arq, exc)
            sys.exit(1)

        total_linhas = 0
        for nome_tabela, contagem in resultados:
            total_linhas += contagem
            unidade = "linha" if contagem == 1 else "linhas"
            nome_qual = f"marts.{nome_tabela}"
            logger.info("✓ %-34s %8s %s", nome_qual, formatar_milhar(contagem), unidade)

        resumo_marts = f"{len(resultados)} marts"
        logger.info("  %-34s %8s linhas", resumo_marts, formatar_milhar(total_linhas))
        return total_linhas
    finally:
        con.close()


if __name__ == "__main__":
    executar_marts()
