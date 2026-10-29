"""Testes unitários do módulo `pipeline/transformacao.py`."""

from decimal import Decimal
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from pipeline import db, transformacao


def _popular_raw_sintetico(con: duckdb.DuckDBPyConnection) -> None:
    db.criar_schema(con, "raw")

    # 3 linhas em despesas_ceap, sendo 2 cópias idênticas (duplicata exata) e 1 de liderança (sgUF = 'NA')
    df_despesas = pd.DataFrame(
        [
            # Linha 1: despesa normal de deputado com CNPJ formatado e zero à esquerda
            {
                "ideDocumento": "100",
                "txNomeParlamentar": "Dep Alfa",
                "ideCadastro": "101",
                "sgUF": "SP",
                "sgPartido": "PARTA",
                "codLegislatura": "57",
                "numSubCota": "1",
                "txtDescricao": "DIVULGACAO",
                "txtFornecedor": "Fornecedor Zero Ltda",
                "txtCNPJCPF": "01.234.567/0001-99",
                "txtNumero": "NF1",
                "indTipoDocumento": "0",
                "datEmissao": "2025-04-10T14:30:00",
                "vlrDocumento": "1000.00",
                "vlrGlosa": "50.00",
                "vlrLiquido": "950.00",
                "numAno": "2025",
                "numMes": "4",
                "numParcela": "0",
                "numLote": "10",
                "nuDeputadoId": "501",
            },
            # Linha 2: cópia exata da linha 1 — deve ser deduplicada
            {
                "ideDocumento": "100",
                "txNomeParlamentar": "Dep Alfa",
                "ideCadastro": "101",
                "sgUF": "SP",
                "sgPartido": "PARTA",
                "codLegislatura": "57",
                "numSubCota": "1",
                "txtDescricao": "DIVULGACAO",
                "txtFornecedor": "Fornecedor Zero Ltda",
                "txtCNPJCPF": "01.234.567/0001-99",
                "txtNumero": "NF1",
                "indTipoDocumento": "0",
                "datEmissao": "2025-04-10T14:30:00",
                "vlrDocumento": "1000.00",
                "vlrGlosa": "50.00",
                "vlrLiquido": "950.00",
                "numAno": "2025",
                "numMes": "4",
                "numParcela": "0",
                "numLote": "10",
                "nuDeputadoId": "501",
            },
            # Linha 3: gasto de Liderança Partidária com sgUF = 'NA' e datEmissao nula (TELEFONIA)
            {
                "ideDocumento": "0",
                "txNomeParlamentar": "LID.GOV",
                "ideCadastro": None,
                "sgUF": "NA",
                "sgPartido": None,
                "codLegislatura": "57",
                "numSubCota": "10",
                "txtDescricao": "TELEFONIA",
                "txtFornecedor": "CELULAR FUNCIONAL",
                "txtCNPJCPF": "00.000.000/0000-01",
                "txtNumero": "FAT99",
                "indTipoDocumento": "0",
                "datEmissao": None,
                "vlrDocumento": "200.25",
                "vlrGlosa": "0.00",
                "vlrLiquido": "200.25",
                "numAno": "2025",
                "numMes": "4",
                "numParcela": "0",
                "numLote": "0",
                "nuDeputadoId": "999",
            },
        ]
    )
    db.gravar(con, df_despesas, "raw", "despesas_ceap")

    df_deputados = pd.DataFrame(
        [
            {
                "uri": "https://dadosabertos.camara.leg.br/api/v2/deputados/101",
                "nome": "Dep Alfa",
                "nomeCivil": "ALFA DA SILVA",
                "idLegislaturaInicial": "56",
                "idLegislaturaFinal": "57",
                "siglaSexo": "F",
                "dataNascimento": "1980-05-15",
                "dataFalecimento": None,
                "ufNascimento": "SP",
                "municipioNascimento": "São Paulo",
            }
        ]
    )
    db.gravar(con, df_deputados, "raw", "deputados")

    df_ceis = pd.DataFrame(
        [
            {
                "CÓDIGO DA SANÇÃO": "SANC-1",
                "TIPO DE PESSOA": "J",
                "CPF OU CNPJ DO SANCIONADO": "01.234.567/0001-99",
                "NOME DO SANCIONADO": "Fornecedor Zero Ltda",
                "RAZÃO SOCIAL - CADASTRO RECEITA": "Fornecedor Zero Ltda",
                "CATEGORIA DA SANÇÃO": "Suspensão",
                "DATA INÍCIO SANÇÃO": "01/01/2025",
                "DATA FINAL SANÇÃO": "31/12/2025",
                "DATA PUBLICAÇÃO": "02/01/2025",
                "ABRAGÊNCIA DA SANÇÃO": "Todos os Poderes",
                "ÓRGÃO SANCIONADOR": "CGU",
                "UF ÓRGÃO SANCIONADOR": "DF",
                "ESFERA ÓRGÃO SANCIONADOR": "Federal",
            }
        ]
    )
    db.gravar(con, df_ceis, "raw", "sancoes_ceis")

    df_uf = pd.DataFrame(
        [
            {
                "codigo_ibge_uf": "35",
                "sigla_uf": "SP",
                "nome_uf": "São Paulo",
                "regiao": "Sudeste",
                "limite_mensal_cota": "41150.25",
            }
        ]
    )
    db.gravar(con, df_uf, "raw", "cotas_uf")


def test_transformacao_deduplica_converte_tipos_e_trata_uf_na(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    banco = tmp_path / "teste.duckdb"
    monkeypatch.setattr(db, "CAMINHO_BANCO", banco)

    con = db.conectar()
    try:
        _popular_raw_sintetico(con)
    finally:
        con.close()

    total = transformacao.executar_transformacao()
    assert total == 5  # 2 despesas (1 duplicata removida) + 1 deputado + 1 ceis + 1 uf

    con = db.conectar()
    try:
        tipos = {r[0]: r[1] for r in con.execute("DESCRIBE refined.despesas_ceap").fetchall()}
        soma_liq = con.execute("SELECT sum(valor_liquido) FROM refined.despesas_ceap").fetchall()[0][0]
        uf_lid = con.execute(
            "SELECT uf FROM refined.despesas_ceap WHERE nome_parlamentar = 'LID.GOV'"
        ).fetchall()[0][0]
        doc_limpo = con.execute(
            "SELECT documento_fornecedor FROM refined.despesas_ceap WHERE documento_id = '100'"
        ).fetchall()[0][0]
    finally:
        con.close()

    assert tipos["data_emissao"] == "TIMESTAMP"
    assert tipos["valor_liquido"] == "DECIMAL(12,2)"
    assert soma_liq == Decimal("1150.25")
    assert uf_lid is None
    assert doc_limpo == "01234567000199"


def test_transformacao_data_invalida_encerra_sem_fabricar_nulo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    banco = tmp_path / "teste.duckdb"
    monkeypatch.setattr(db, "CAMINHO_BANCO", banco)

    con = db.conectar()
    try:
        _popular_raw_sintetico(con)
        # Injeta uma data fora do formato declarado '%Y-%m-%d'
        con.execute("UPDATE raw.deputados SET dataNascimento = '15/05/1980'")
    finally:
        con.close()

    with pytest.raises(SystemExit) as exc:
        transformacao.executar_transformacao()
    assert exc.value.code == 1


def test_transformacao_sem_raw_encerra_com_erro(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(db, "CAMINHO_BANCO", tmp_path / "vazio.duckdb")
    with pytest.raises(SystemExit) as exc:
        transformacao.executar_transformacao()
    assert exc.value.code == 1
