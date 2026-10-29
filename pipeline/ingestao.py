"""Etapa 1 — Ingestão dos arquivos brutos (.csv.gz) para o schema `raw` do DuckDB.

SPEC DO MÓDULO (Fonte da Verdade):
1. ESCOPO E NOMES (schema `raw`):
   - despesas_ceap.csv.gz -> raw.despesas_ceap
   - deputados.csv.gz     -> raw.deputados
   - sancoes_ceis.csv.gz  -> raw.sancoes_ceis
   - sancoes_cnep.csv.gz  -> raw.sancoes_cnep
   - cotas_uf.csv.gz      -> raw.cotas_uf
   Motivo: vocabulário em português, claro e conciso para os JOINs das próximas etapas.

2. PROIBIÇÕES:
   Nenhuma conversão de tipo, nenhuma linha descartada ou deduplicada, nenhum nome
   de coluna alterado e nenhum valor corrigido.
   Motivo: manter a fronteira estrita entre o dado bruto oficial e o dado decidido
   na etapa 2 (refined).

3. TIPAGEM E LEITURA:
   Toda coluna entra como VARCHAR (dtype=str), encoding="utf-8", campo vazio vira NULL.
   Motivo: impedir que inferência de tipo apague zeros à esquerda em CNPJ/CPF
   (ex.: 085.324.290/0013-1 ou 03316005870).

4. REEXECUÇÃO E ERRO:
   Idempotente (CREATE OR REPLACE TABLE). Antes de abrir o banco, confere a existência
   dos cinco arquivos em PASTA_RAW; se faltar qualquer um, lista todos os ausentes e
   encerra com sys.exit(1) sem gravar parcialmente.
"""

import sys
import pandas as pd
from pipeline import db

MAPA_ARQUIVOS: tuple[tuple[str, str], ...] = (
    ("despesas_ceap.csv.gz", "despesas_ceap"),
    ("deputados.csv.gz", "deputados"),
    ("sancoes_ceis.csv.gz", "sancoes_ceis"),
    ("sancoes_cnep.csv.gz", "sancoes_cnep"),
    ("cotas_uf.csv.gz", "cotas_uf"),
)


def formatar_milhar(valor: int) -> str:
    """Formata inteiro usando ponto como separador de milhar."""
    return f"{valor:,}".replace(",", ".")


def verificar_arquivos() -> None:
    """Verifica se todos os arquivos brutos existem antes de tocar no banco."""
    faltantes = [
        arquivo for arquivo, _ in MAPA_ARQUIVOS if not (db.PASTA_RAW / arquivo).is_file()
    ]
    if faltantes:
        print(
            f"Erro: arquivos obrigatórios não encontrados na pasta {db.PASTA_RAW}:",
            file=sys.stderr,
        )
        for arq in faltantes:
            print(f"  - {arq}", file=sys.stderr)
        sys.exit(1)


def executar_ingestao() -> int:
    """Executa a ingestão completa para o schema raw e devolve o total de linhas gravadas."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    verificar_arquivos()

    con = db.conectar()
    try:
        db.criar_schema(con, "raw")
        total = 0
        for arquivo, tabela in MAPA_ARQUIVOS:
            caminho = db.PASTA_RAW / arquivo
            # keep_default_na=False + na_values=[""] evita que strings como "NA" virem nulo,
            # convertendo apenas campos realmente vazios em NULL.
            df = pd.read_csv(
                caminho,
                encoding="utf-8",
                dtype=str,
                keep_default_na=False,
                na_values=[""],
            )
            contagem = db.gravar(con, df, "raw", tabela)
            total += contagem
            nome_qualificado = f"raw.{tabela}"
            print(f"✓ {nome_qualificado:<22} {formatar_milhar(contagem):>10} linhas")

        print(f"  {'total':<22} {formatar_milhar(total):>10} linhas")
        return total
    finally:
        con.close()


if __name__ == "__main__":
    executar_ingestao()
