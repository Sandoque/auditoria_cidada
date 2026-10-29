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

# Limites mensais oficiais da Cota Parlamentar (CEAP) por UF (Ato da Mesa da Câmara, em R$)
COTAS_MENSAIS_UF = {
    "AC": ("50426.26", "Norte"),
    "AL": ("44632.46", "Nordeste"),
    "AM": ("48793.25", "Norte"),
    "AP": ("49168.58", "Norte"),
    "BA": ("42951.99", "Nordeste"),
    "CE": ("45954.86", "Nordeste"),
    "DF": ("36582.46", "Centro-Oeste"),
    "ES": ("41212.01", "Sudeste"),
    "GO": ("40971.77", "Centro-Oeste"),
    "MA": ("47657.66", "Nordeste"),
    "MG": ("39896.81", "Sudeste"),
    "MS": ("44289.11", "Centro-Oeste"),
    "MT": ("43440.12", "Centro-Oeste"),
    "PA": ("47539.10", "Norte"),
    "PB": ("45303.85", "Nordeste"),
    "PE": ("44979.43", "Nordeste"),
    "PI": ("45849.65", "Nordeste"),
    "PR": ("42451.77", "Sul"),
    "RJ": ("39928.60", "Sudeste"),
    "RN": ("46179.96", "Nordeste"),
    "RO": ("49466.29", "Norte"),
    "RR": ("51406.33", "Norte"),
    "RS": ("44652.41", "Sul"),
    "SC": ("43672.49", "Sul"),
    "SE": ("43974.74", "Nordeste"),
    "SP": ("41150.25", "Sudeste"),
    "TO": ("43570.16", "Norte"),
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
