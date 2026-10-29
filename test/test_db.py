"""Testes unitários do módulo `pipeline/db.py`."""

from pathlib import Path

import pandas as pd
import pytest

from pipeline import db


def test_conectar_cria_banco_no_caminho_configurado(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    banco_temp = tmp_path / "teste.duckdb"
    monkeypatch.setattr(db, "CAMINHO_BANCO", banco_temp)

    con = db.conectar()
    try:
        assert banco_temp.is_file()
    finally:
        con.close()


def test_gravar_recria_tabela_de_forma_idempotente(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(db, "CAMINHO_BANCO", tmp_path / "teste.duckdb")
    df = pd.DataFrame(
        [
            # Linha 1: CNPJ com zero à esquerda como texto
            {"doc": "01234567000199", "valor": "100.50"},
            # Linha 2: registro com valor nulo
            {"doc": "98765432000100", "valor": None},
            # Linha 3: CPF com zero à esquerda
            {"doc": "00011122233", "valor": "50.00"},
        ]
    )

    con = db.conectar()
    try:
        primeira_contagem = db.gravar(con, df, "raw", "amostra")
        segunda_contagem = db.gravar(con, df, "raw", "amostra")
        nulos_valor = con.execute(
            "SELECT count(*) - count(valor) FROM raw.amostra"
        ).fetchall()[0][0]
    finally:
        con.close()

    assert primeira_contagem == 3
    assert segunda_contagem == 3
    assert nulos_valor == 1


def test_validar_identificador_rejeita_nome_invalido(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(db, "CAMINHO_BANCO", tmp_path / "teste.duckdb")
    con = db.conectar()
    try:
        with pytest.raises(ValueError):
            db.criar_schema(con, "schema-invalido; DROP TABLE x")
    finally:
        con.close()
