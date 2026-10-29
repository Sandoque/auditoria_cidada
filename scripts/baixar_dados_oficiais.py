"""Script utilitário para baixar os dados brutos oficiais dos portais de Dados Abertos
(Câmara dos Deputados, Portal da Transparência CGU e IBGE) e gravar em raw/*.csv.gz
em UTF-8 sem alterar nenhum valor, linha ou nome de coluna original.
"""

import gzip
import io
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RAIZ = Path(__file__).resolve().parent.parent
PASTA_RAW = RAIZ / "raw"
HEADERS = {"User-Agent": "Mozilla/5.0 (Auditoria-Cidada-Pipeline/1.0)"}

# Limites mensais oficiais da Cota Parlamentar (CEAP) por UF, em R$: Anexo I do Ato da Mesa
# n. 270, de 19/01/2023, vigente de 01/02/2023 até o reajuste do Ato da Mesa n. 244, de
# 20/02/2026 — ou seja, o ano de 2025 inteiro. Fonte:
# https://www2.camara.leg.br/legin/int/atomes/2023/atodamesa-270-19-janeiro-2023-793708-anexo-cd-mesa.pdf
COTAS_MENSAIS_UF = {
    "AC": ("50426.26", "Norte"),
    "AL": ("46737.90", "Nordeste"),
    "AM": ("49363.92", "Norte"),
    "AP": ("49168.58", "Norte"),
    "BA": ("44804.65", "Nordeste"),
    "CE": ("48245.57", "Nordeste"),
    "DF": ("36582.46", "Centro-Oeste"),
    "ES": ("43217.71", "Sudeste"),
    "GO": ("41300.86", "Centro-Oeste"),
    "MA": ("47945.49", "Nordeste"),
    "MG": ("41886.51", "Sudeste"),
    "MS": ("46336.64", "Centro-Oeste"),
    "MT": ("45221.83", "Centro-Oeste"),
    "PA": ("48021.25", "Norte"),
    "PB": ("47826.36", "Nordeste"),
    "PE": ("47470.60", "Nordeste"),
    "PI": ("46765.57", "Nordeste"),
    "PR": ("44665.66", "Sul"),
    "RJ": ("41553.77", "Sudeste"),
    "RN": ("48525.79", "Nordeste"),
    "RO": ("49466.29", "Norte"),
    "RR": ("51406.33", "Norte"),
    "RS": ("46669.70", "Sul"),
    "SC": ("45671.58", "Sul"),
    "SE": ("45933.06", "Nordeste"),
    "SP": ("42837.33", "Sudeste"),
    "TO": ("45297.41", "Norte"),
}


def baixar_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=90) as resp:
        return resp.read()


def main() -> None:
    PASTA_RAW.mkdir(parents=True, exist_ok=True)

    # 1. CEAP 2025 - Câmara dos Deputados
    print("Baixando CEAP 2025 (Câmara dos Deputados)...")
    ceap_zip = baixar_bytes("https://www.camara.leg.br/cotas/Ano-2025.csv.zip")
    with zipfile.ZipFile(io.BytesIO(ceap_zip)) as z:
        df_ceap = pd.read_csv(
            io.BytesIO(z.read(z.namelist()[0])),
            sep=";",
            encoding="utf-8-sig",
            dtype=str,
            keep_default_na=False,
        )
    df_ceap.replace("", None).to_csv(
        PASTA_RAW / "despesas_ceap.csv.gz", index=False, encoding="utf-8", compression="gzip"
    )
    print(f"  ✓ despesas_ceap.csv.gz: {len(df_ceap):,} linhas")

    # 2. Deputados - Câmara dos Deputados
    print("Baixando cadastro de Deputados (Câmara dos Deputados)...")
    dep_bytes = baixar_bytes("https://dadosabertos.camara.leg.br/arquivos/deputados/csv/deputados.csv")
    df_dep = pd.read_csv(
        io.BytesIO(dep_bytes),
        sep=";",
        encoding="utf-8-sig",
        dtype=str,
        keep_default_na=False,
    )
    df_dep.replace("", None).to_csv(
        PASTA_RAW / "deputados.csv.gz", index=False, encoding="utf-8", compression="gzip"
    )
    print(f"  ✓ deputados.csv.gz: {len(df_dep):,} linhas")

    # 3. CEIS - Portal da Transparência CGU
    print("Baixando CEIS (Portal da Transparência CGU)...")
    ceis_zip = baixar_bytes("https://portaldatransparencia.gov.br/download-de-dados/ceis/20261029")
    with zipfile.ZipFile(io.BytesIO(ceis_zip)) as z:
        df_ceis = pd.read_csv(
            io.BytesIO(z.read(z.namelist()[0])),
            sep=";",
            encoding="cp1252",
            dtype=str,
            keep_default_na=False,
        )
    df_ceis.replace("", None).to_csv(
        PASTA_RAW / "sancoes_ceis.csv.gz", index=False, encoding="utf-8", compression="gzip"
    )
    print(f"  ✓ sancoes_ceis.csv.gz: {len(df_ceis):,} linhas")

    # 4. CNEP - Portal da Transparência CGU
    print("Baixando CNEP (Portal da Transparência CGU)...")
    cnep_zip = baixar_bytes("https://portaldatransparencia.gov.br/download-de-dados/cnep/20261029")
    with zipfile.ZipFile(io.BytesIO(cnep_zip)) as z:
        df_cnep = pd.read_csv(
            io.BytesIO(z.read(z.namelist()[0])),
            sep=";",
            encoding="cp1252",
            dtype=str,
            keep_default_na=False,
        )
    df_cnep.replace("", None).to_csv(
        PASTA_RAW / "sancoes_cnep.csv.gz", index=False, encoding="utf-8", compression="gzip"
    )
    print(f"  ✓ sancoes_cnep.csv.gz: {len(df_cnep):,} linhas")

    # 5. Estados IBGE + Limite Mensal Cota UF
    print("Baixando Estados (API IBGE) + Tabela Oficial de Limites de Cota por UF...")
    uf_bytes = baixar_bytes("https://servicodados.ibge.gov.br/api/v1/localidades/estados")
    if uf_bytes[:2] == b"\x1f\x8b":
        uf_bytes = gzip.decompress(uf_bytes)
    uf_lista = json.loads(uf_bytes.decode("utf-8"))
    linhas_uf = []
    for row in sorted(uf_lista, key=lambda x: x["sigla"]):
        sigla = str(row["sigla"])
        cota, regiao = COTAS_MENSAIS_UF[sigla]
        linhas_uf.append(
            {
                "codigo_ibge_uf": str(row["id"]),
                "sigla_uf": sigla,
                "nome_uf": str(row["nome"]),
                "regiao": regiao,
                "limite_mensal_cota": cota,
            }
        )
    df_uf = pd.DataFrame(linhas_uf, dtype=str)
    df_uf.to_csv(
        PASTA_RAW / "cotas_uf.csv.gz", index=False, encoding="utf-8", compression="gzip"
    )
    print(f"  ✓ cotas_uf.csv.gz: {len(df_uf):,} linhas")


if __name__ == "__main__":
    main()
