"""Testes unitários do módulo `pipeline/ingestao.py`."""

from pathlib import Path

import duckdb
import pandas as pd
import pytest

from pipeline import db, ingestao


def _criar_csvs_sinteticos(pasta_raw: Path) -> None:
    pasta_raw.mkdir(parents=True, exist_ok=True)
    # 2 despesas sintéticas, uma com CNPJ começando com zero e outra com campo vazio
    pd.DataFrame(
        [
            {"ideDocumento": "10", "txtCNPJCPF": "01234567000199", "datEmissao": ""},
            {"ideDocumento": "20", "txtCNPJCPF": "11222333000188", "datEmissao": "2025-03-01T00:00:00"},
        ]
    ).to_csv(pasta_raw / "despesas_ceap.csv.gz", index=False, encoding="utf-8", compression="gzip")

    pd.DataFrame([{"uri": "https://camara/deputados/101", "nome": "Deputado A"}]).to_csv(
        pasta_raw / "deputados.csv.gz", index=False, encoding="utf-8", compression="gzip"
    )
    pd.DataFrame([{"CÓDIGO DA SANÇÃO": "S1", "CPF OU CNPJ DO SANCIONADO": "01234567000199"}]).to_csv(
        pasta_raw / "sancoes_ceis.csv.gz", index=False, encoding="utf-8", compression="gzip"
    )
    pd.DataFrame([{"CÓDIGO DA SANÇÃO": "C1", "CPF OU CNPJ DO SANCIONADO": "01234567000199"}]).to_csv(
        pasta_raw / "sancoes_cnep.csv.gz", index=False, encoding="utf-8", compression="gzip"
    )
    pd.DataFrame([{"codigo_ibge_uf": "35", "sigla_uf": "SP"}]).to_csv(
        pasta_raw / "cotas_uf.csv.gz", index=False, encoding="utf-8", compression="gzip"
    )
    # Limite com vigência e um evento de mandato (Etapa 6), também gravados sem conversão
    pd.DataFrame([{"sigla_uf": "SP", "vigencia_inicio": "2023-02-01", "limite_mensal_cota": "1000.00"}]).to_csv(
        pasta_raw / "limites_cota_uf.csv.gz", index=False, encoding="utf-8", compression="gzip"
    )
    pd.DataFrame([{"id": "101", "dataHora": "2023-02-01T12:05", "descricaoStatus": "Entrada - Posse"}]).to_csv(
        pasta_raw / "historico_deputados.csv.gz", index=False, encoding="utf-8", compression="gzip"
    )


def test_ingestao_grava_sete_tabelas_como_varchar_e_preserva_zero_a_esquerda(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pasta_raw = tmp_path / "raw"
    banco_temp = tmp_path / "teste.duckdb"
    _criar_csvs_sinteticos(pasta_raw)
    monkeypatch.setattr(db, "PASTA_RAW", pasta_raw)
    monkeypatch.setattr(db, "CAMINHO_BANCO", banco_temp)

    total_1 = ingestao.executar_ingestao()
    total_2 = ingestao.executar_ingestao()

    con = duckdb.connect(str(banco_temp), read_only=True)
    try:
        tipos = {
            r[0]: r[1]
            for r in con.execute("DESCRIBE raw.despesas_ceap").fetchall()
        }
        cnpj = con.execute(
            "SELECT txtCNPJCPF FROM raw.despesas_ceap WHERE ideDocumento = '10'"
        ).fetchall()[0][0]
        nulos_data = con.execute(
            "SELECT count(*) - count(datEmissao) FROM raw.despesas_ceap"
        ).fetchall()[0][0]
    finally:
        con.close()

    assert total_1 == 8
    assert total_2 == 8
    assert all(t == "VARCHAR" for t in tipos.values())
    assert cnpj == "01234567000199"
    assert nulos_data == 1


def test_ingestao_arquivo_faltando_encerra_sem_criar_banco(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pasta_raw = tmp_path / "raw_incompleta"
    pasta_raw.mkdir(parents=True, exist_ok=True)
    banco_temp = tmp_path / "nao_deve_existir.duckdb"
    monkeypatch.setattr(db, "PASTA_RAW", pasta_raw)
    monkeypatch.setattr(db, "CAMINHO_BANCO", banco_temp)

    with pytest.raises(SystemExit) as exc:
        ingestao.executar_ingestao()

    assert exc.value.code == 1
    assert not banco_temp.exists()
