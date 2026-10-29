"""Script utilitário para baixar os dados brutos oficiais dos portais de Dados Abertos
(Câmara dos Deputados, Portal da Transparência CGU e IBGE) e gravar em raw/*.csv.gz
em UTF-8 sem alterar nenhum valor, linha ou nome de coluna original.

- CEAP: um arquivo por ano na Câmara (de ANO_INICIAL até o ano corrente), empilhados em
  despesas_ceap.csv.gz; a coluna numAno identifica o ano de cada lançamento.
- CEIS/CNEP: a CGU só publica o arquivo do dia; tenta hoje e, se ainda não saiu, ontem
  (datas no fuso de Brasília).
- Histórico de mandatos: /api/v2/deputados/{id}/historico de cada deputado presente na
  CEAP, para medir os dias de efetivo exercício (art. 11 do Ato da Mesa n. 43/2009).
- Limites da cota: tabela oficial por UF e período de vigência, digitada a partir dos
  atos da Mesa (não há arquivo de dados abertos para ela).
"""

import gzip
import io
import json
import sys
import time
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RAIZ = Path(__file__).resolve().parent.parent
PASTA_RAW = RAIZ / "raw"
HEADERS = {"User-Agent": "Mozilla/5.0 (Auditoria-Cidada-Pipeline/1.0)"}
FUSO_BRASILIA = timezone(timedelta(hours=-3))
ANO_INICIAL = 2025

REGIOES_UF = {
    "AC": "Norte", "AL": "Nordeste", "AM": "Norte", "AP": "Norte", "BA": "Nordeste",
    "CE": "Nordeste", "DF": "Centro-Oeste", "ES": "Sudeste", "GO": "Centro-Oeste",
    "MA": "Nordeste", "MG": "Sudeste", "MS": "Centro-Oeste", "MT": "Centro-Oeste",
    "PA": "Norte", "PB": "Nordeste", "PE": "Nordeste", "PI": "Nordeste", "PR": "Sul",
    "RJ": "Sudeste", "RN": "Nordeste", "RO": "Norte", "RR": "Norte", "RS": "Sul",
    "SC": "Sul", "SE": "Nordeste", "SP": "Sudeste", "TO": "Norte",
}

# Limites mensais oficiais da Cota Parlamentar (CEAP) por UF, em R$, por início de vigência.
# - 2023-02-01: Anexo I do Ato da Mesa n. 270, de 19/01/2023 (em vigor em 01/02/2023).
#   https://www2.camara.leg.br/legin/int/atomes/2023/atodamesa-270-19-janeiro-2023-793708-anexo-cd-mesa.pdf
# - 2026-02-20: Ato da Mesa n. 244, de 20/02/2026 (em vigor na publicação), que corrigiu os
#   limites pelo IPCA de fev/2023 a dez/2025 (fator 1,1375). Valores conferidos na página
#   "Cota Parlamentar" do Guia para Jornalistas da Câmara:
#   https://www2.camara.leg.br/comunicacao/assessoria-de-imprensa/guia-para-jornalistas/cota-parlamentar
LIMITES_COTA_UF: dict[str, tuple[str, dict[str, str]]] = {
    "2023-02-01": (
        "270/2023",
        {
            "AC": "50426.26", "AL": "46737.90", "AM": "49363.92", "AP": "49168.58",
            "BA": "44804.65", "CE": "48245.57", "DF": "36582.46", "ES": "43217.71",
            "GO": "41300.86", "MA": "47945.49", "MG": "41886.51", "MS": "46336.64",
            "MT": "45221.83", "PA": "48021.25", "PB": "47826.36", "PE": "47470.60",
            "PI": "46765.57", "PR": "44665.66", "RJ": "41553.77", "RN": "48525.79",
            "RO": "49466.29", "RR": "51406.33", "RS": "46669.70", "SC": "45671.58",
            "SE": "45933.06", "SP": "42837.33", "TO": "45297.41",
        },
    ),
    "2026-02-20": (
        "244/2026",
        {
            "AC": "57359.87", "AL": "53164.36", "AM": "56151.46", "AP": "55929.26",
            "BA": "50965.29", "CE": "54879.34", "DF": "41612.55", "ES": "49160.15",
            "GO": "46979.73", "MA": "54537.99", "MG": "47645.91", "MS": "52707.93",
            "MT": "51439.83", "PA": "54624.17", "PB": "54402.48", "PE": "53997.81",
            "PI": "53195.84", "PR": "50807.19", "RJ": "47267.41", "RN": "55198.09",
            "RO": "56267.90", "RR": "58474.70", "RS": "53086.78", "SC": "51951.42",
            "SE": "52248.86", "SP": "48727.46", "TO": "51525.80",
        },
    ),
}


def baixar_bytes(url: str, tentativas: int = 3) -> bytes:
    for tentativa in range(1, tentativas + 1):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=90) as resp:
                return resp.read()
        except (urllib.error.URLError, TimeoutError):
            if tentativa == tentativas:
                raise
            time.sleep(2 * tentativa)
    raise RuntimeError("inalcançável")


def baixar_zip_cgu(cadastro: str) -> tuple[bytes, str]:
    """A CGU só mantém o arquivo do dia: tenta hoje e, se ainda não foi publicado, ontem."""
    hoje = datetime.now(FUSO_BRASILIA).date()
    for dia in (hoje, hoje - timedelta(days=1)):
        data = dia.strftime("%Y%m%d")
        try:
            return baixar_bytes(f"https://portaldatransparencia.gov.br/download-de-dados/{cadastro}/{data}"), data
        except urllib.error.HTTPError:
            continue
    raise RuntimeError(f"{cadastro.upper()} indisponível na CGU para {hoje} e para o dia anterior")


def ler_csv_do_zip(conteudo: bytes, encoding: str) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
        return pd.read_csv(
            io.BytesIO(z.read(z.namelist()[0])),
            sep=";",
            encoding=encoding,
            dtype=str,
            keep_default_na=False,
        )


def gravar_raw(df: pd.DataFrame, arquivo: str) -> None:
    df.replace("", None).to_csv(PASTA_RAW / arquivo, index=False, encoding="utf-8", compression="gzip")
    print(f"  ✓ {arquivo}: {len(df):,} linhas")


def baixar_historico(deputado_id: str) -> list[dict]:
    url = f"https://dadosabertos.camara.leg.br/api/v2/deputados/{deputado_id}/historico"
    return json.loads(baixar_bytes(url).decode("utf-8"))["dados"]


def main() -> None:
    PASTA_RAW.mkdir(parents=True, exist_ok=True)
    ano_corrente = datetime.now(FUSO_BRASILIA).year

    # 1. CEAP de ANO_INICIAL até o ano corrente - Câmara dos Deputados
    partes = []
    for ano in range(ANO_INICIAL, ano_corrente + 1):
        print(f"Baixando CEAP {ano} (Câmara dos Deputados)...")
        partes.append(ler_csv_do_zip(baixar_bytes(f"https://www.camara.leg.br/cotas/Ano-{ano}.csv.zip"), "utf-8-sig"))
    if any(list(p.columns) != list(partes[0].columns) for p in partes):
        raise RuntimeError("Os arquivos anuais da CEAP vieram com colunas diferentes entre si")
    df_ceap = pd.concat(partes, ignore_index=True)
    gravar_raw(df_ceap, "despesas_ceap.csv.gz")

    # 2. Deputados - Câmara dos Deputados
    print("Baixando cadastro de Deputados (Câmara dos Deputados)...")
    dep_bytes = baixar_bytes("https://dadosabertos.camara.leg.br/arquivos/deputados/csv/deputados.csv")
    df_dep = pd.read_csv(io.BytesIO(dep_bytes), sep=";", encoding="utf-8-sig", dtype=str, keep_default_na=False)
    gravar_raw(df_dep, "deputados.csv.gz")

    # 3 e 4. CEIS e CNEP - Portal da Transparência CGU
    for cadastro in ("ceis", "cnep"):
        conteudo, data = baixar_zip_cgu(cadastro)
        print(f"Baixando {cadastro.upper()} de {data} (Portal da Transparência CGU)...")
        gravar_raw(ler_csv_do_zip(conteudo, "cp1252"), f"sancoes_{cadastro}.csv.gz")

    # 5. Estados IBGE (cadastro das UFs)
    print("Baixando Estados (API IBGE)...")
    uf_bytes = baixar_bytes("https://servicodados.ibge.gov.br/api/v1/localidades/estados")
    if uf_bytes[:2] == b"\x1f\x8b":
        uf_bytes = gzip.decompress(uf_bytes)
    df_uf = pd.DataFrame(
        [
            {
                "codigo_ibge_uf": str(row["id"]),
                "sigla_uf": str(row["sigla"]),
                "nome_uf": str(row["nome"]),
                "regiao": REGIOES_UF[str(row["sigla"])],
            }
            for row in sorted(json.loads(uf_bytes.decode("utf-8")), key=lambda x: x["sigla"])
        ],
        dtype=str,
    )
    gravar_raw(df_uf, "cotas_uf.csv.gz")

    # 6. Limites mensais da cota por UF e vigência (atos da Mesa)
    print("Gravando limites da cota por UF e vigência (Atos da Mesa n. 270/2023 e 244/2026)...")
    df_limites = pd.DataFrame(
        [
            {"sigla_uf": uf, "vigencia_inicio": inicio, "limite_mensal_cota": valor, "ato_da_mesa": ato}
            for inicio, (ato, valores) in LIMITES_COTA_UF.items()
            for uf, valor in valores.items()
        ],
        dtype=str,
    )
    gravar_raw(df_limites, "limites_cota_uf.csv.gz")

    # 7. Histórico de mandatos de cada deputado com despesa na CEAP - API da Câmara
    ids = sorted(df_ceap["ideCadastro"].replace("", None).dropna().unique(), key=int)
    print(f"Baixando histórico de mandato de {len(ids)} deputados (API da Câmara)...")
    with ThreadPoolExecutor(max_workers=4) as executor:
        eventos = [evento for lista in executor.map(baixar_historico, ids) for evento in lista]
    df_hist = pd.DataFrame(eventos, dtype=object).map(lambda v: None if v is None else str(v))
    gravar_raw(df_hist, "historico_deputados.csv.gz")


if __name__ == "__main__":
    main()
