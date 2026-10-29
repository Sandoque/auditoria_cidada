"""Executor completo do pipeline do zero (saída de emergência / reconstrução total).

Apaga o arquivo auditoria.duckdb se existir e executa em sequência:
1. pipeline.ingestao      (CSV -> raw)
2. pipeline.transformacao (raw -> refined)
3. pipeline.marts         (refined -> marts)
4. pipeline.qualidade     (validação de invariantes de qualidade de dados)
5. relatorio              (geração de relatorio.html)
"""

import sys

import relatorio
from pipeline import db, ingestao, marts, qualidade, transformacao


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if db.CAMINHO_BANCO.is_file():
        db.CAMINHO_BANCO.unlink()

    print("=== 1/5 · Ingestão (raw) ===")
    ingestao.executar_ingestao()

    print("\n=== 2/5 · Transformação (refined) ===")
    transformacao.executar_transformacao()

    print("\n=== 3/5 · Marts (SQL) ===")
    marts.executar_marts()

    print("\n=== 4/5 · Qualidade de Dados ===")
    qualidade.executar_qualidade()

    print("\n=== 5/5 · Relatório Estático (HTML) ===")
    relatorio.gerar_relatorio()


if __name__ == "__main__":
    main()
