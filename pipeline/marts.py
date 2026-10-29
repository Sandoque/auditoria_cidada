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
   - Verifica se as quatro tabelas de `refined` existem antes de começar.
   - Valida que todos os arquivos seguem o padrão `NN_nome.sql` e que não há nomes
     de tabela repetidos antes de tocar no schema `marts`.
   - Executa `DROP SCHEMA`, `CREATE SCHEMA` e todos os `CREATE TABLE` dentro de uma
     única transação: se qualquer SQL falhar ou produzir 0 linhas, faz `ROLLBACK` e
     encerra com `sys.exit(1)`, preservando o estado anterior do schema `marts`.
"""

import re
import sys
from pathlib import Path

import duckdb
from pipeline import db

PASTA_MARTS = db.RAIZ_PROJETO / "sql" / "marts"
TABELAS_REFINED_OBRIGATORIAS: tuple[str, ...] = (
    "despesas_ceap",
    "deputados",
    "sancoes_ceis",
    "cotas_uf",
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
        print(
            "Erro: tabelas obrigatórias ausentes no schema refined: "
            + ", ".join(f"refined.{t}" for t in faltantes)
            + ". Rode 'uv run python -m pipeline.transformacao' antes dos marts.",
            file=sys.stderr,
        )
        sys.exit(1)


def listar_e_validar_arquivos(pasta: Path) -> list[tuple[Path, str]]:
    if not pasta.is_dir():
        print(f"Erro: pasta de marts não encontrada: {pasta}", file=sys.stderr)
        sys.exit(1)

    arquivos = sorted(pasta.glob("*.sql"))
    if not arquivos:
        print(f"Erro: nenhum arquivo .sql encontrado em {pasta}", file=sys.stderr)
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
            print(
                "Erro: arquivos sem o prefixo obrigatório NN_nome.sql: "
                + ", ".join(invalidos),
                file=sys.stderr,
            )
        if duplicados:
            for nome_tab, arqs in duplicados.items():
                print(
                    f"Erro: múltiplos arquivos geram a mesma tabela marts.{nome_tab}: "
                    + ", ".join(arqs),
                    file=sys.stderr,
                )
        sys.exit(1)

    return plano


def executar_marts() -> int:
    """Executa todos os arquivos sql/marts/*.sql e devolve a soma de linhas dos marts."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

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
        except Exception as exc:
            try:
                con.execute("ROLLBACK")
            except Exception:
                pass
            nome_arq = caminho_sql.name if "caminho_sql" in locals() else "<desconhecido>"
            print(f"Erro ao executar {nome_arq}: {exc}", file=sys.stderr)
            sys.exit(1)

        total_linhas = 0
        for nome_tabela, contagem in resultados:
            total_linhas += contagem
            unidade = "linha" if contagem == 1 else "linhas"
            nome_qual = f"marts.{nome_tabela}"
            print(f"✓ {nome_qual:<34} {formatar_milhar(contagem):>8} {unidade}")

        resumo_marts = f"{len(resultados)} marts"
        print(f"  {resumo_marts:<34} {formatar_milhar(total_linhas):>8} linhas")
        return total_linhas
    finally:
        con.close()


if __name__ == "__main__":
    executar_marts()
