"""Executor completo do pipeline do zero (saída de emergência / reconstrução total).

Se faltar qualquer arquivo em `raw/`, baixa as fontes oficiais antes de começar.
Apaga o arquivo auditoria.duckdb se existir e executa em sequência:
1. pipeline.ingestao      (CSV -> raw)
2. pipeline.transformacao (raw -> refined)
3. pipeline.marts         (refined -> marts)
4. pipeline.qualidade     (validação de invariantes de qualidade de dados)
5. relatorio              (geração de relatorio.html)
"""

import logging

import relatorio
from pipeline import db, ingestao, marts, qualidade, transformacao
from scripts import baixar_dados_oficiais

logger = logging.getLogger(__name__)


def garantir_dados_brutos() -> None:
    """Baixa os arquivos oficiais se a pasta raw/ ainda não estiver completa."""
    if ingestao.arquivos_faltantes():
        logger.info("=== 0/5 · Download dos dados brutos oficiais (raw) ===")
        baixar_dados_oficiais.main()


def main() -> None:
    db.configurar_logging()
    garantir_dados_brutos()

    if db.CAMINHO_BANCO.is_file():
        db.CAMINHO_BANCO.unlink()

    logger.info("=== 1/5 · Ingestão (raw) ===")
    ingestao.executar_ingestao()

    logger.info("=== 2/5 · Transformação (refined) ===")
    transformacao.executar_transformacao()

    logger.info("=== 3/5 · Marts (SQL) ===")
    marts.executar_marts()

    logger.info("=== 4/5 · Qualidade de Dados ===")
    qualidade.executar_qualidade()

    logger.info("=== 5/5 · Relatório Estático (HTML) ===")
    relatorio.gerar_relatorio()


if __name__ == "__main__":
    main()
