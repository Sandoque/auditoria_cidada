"""Interface web local do DuckDB (`http://localhost:4213`) para exploração em SQL.

SPEC DO MÓDULO (Fonte da Verdade):
- U1. Abre auditoria.duckdb na raiz do projeto, instala/carrega a extensão `ui` e
  executa CALL start_ui().
- U2. Mantém o servidor ativo até Ctrl+C, fechando a conexão sem traceback.
- U3. Se auditoria.duckdb não existir, orienta a rodar a ingestão primeiro e encerra
  com sys.exit(1) sem criar um banco vazio.
- U4. Não importa pipeline.ingestao nem pipeline.db.
"""

import sys
import time
from pathlib import Path

import duckdb

CAMINHO_BANCO = Path(__file__).resolve().parent / "auditoria.duckdb"


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    if not CAMINHO_BANCO.is_file():
        print(
            "Erro: o arquivo auditoria.duckdb ainda não existe. "
            "Rode 'uv run python -m pipeline.ingestao' antes de abrir a interface.",
            file=sys.stderr,
        )
        sys.exit(1)

    con = duckdb.connect(str(CAMINHO_BANCO))
    try:
        con.execute("INSTALL ui; LOAD ui;")
        con.execute("CALL start_ui();")
        print("DuckDB UI ativa em http://localhost:4213 — pressione Ctrl+C para encerrar.")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nEncerrando servidor DuckDB UI e liberando o arquivo auditoria.duckdb.")
    finally:
        con.close()


if __name__ == "__main__":
    main()
