"""Testes unitários do executor `pipeline/marts.py`, dos marts SQL e de `pipeline/qualidade.py`."""

from decimal import Decimal
from pathlib import Path

import duckdb
import pytest

from pipeline import db, marts


def _criar_refined_sintetico(con: duckdb.DuckDBPyConnection) -> None:
    db.criar_schema(con, "refined")
    con.execute("""
        CREATE TABLE refined.despesas_ceap AS
        SELECT * FROM (
            VALUES
            -- Lançamento 1: Dep 101 em SP, fornecedor sancionado (01234567000199), durante vigência
            ('1', 'Dep Alfa', '101', 'SP', 'PA', 57, 1, 'DIVULGACAO', 'Forn Punido', '01234567000199', 'NF1', 0,
             TIMESTAMP '2025-05-10 10:00:00', DECIMAL '1000.00', DECIMAL '100.00', DECIMAL '900.00', 2025, 5, 0, 1, 1),
            -- Lançamento 2: Dep 101 em SP, fornecedor limpo (99888777000166)
            ('2', 'Dep Alfa', '101', 'SP', 'PA', 57, 2, 'COMBUSTIVEL', 'Posto Limpo', '99888777000166', 'NF2', 0,
             TIMESTAMP '2025-05-12 12:00:00', DECIMAL '300.00', DECIMAL '0.00', DECIMAL '300.00', 2025, 5, 0, 1, 1),
            -- Lançamento 3: Bilhete aéreo cancelado com valor negativo — deve ficar fora da receita/despesa válida
            ('3', 'Dep Alfa', '101', 'SP', 'PA', 57, 9, 'PASSAGEM', 'Cia Aerea', '99888777000166', 'NF3', 0,
             TIMESTAMP '2025-05-15 08:00:00', DECIMAL '-500.00', DECIMAL '0.00', DECIMAL '-500.00', 2025, 5, 0, 1, 1)
        ) AS t(
            documento_id, nome_parlamentar, deputado_id, uf, partido, legislatura_id, subcota_id,
            categoria_despesa, nome_fornecedor, documento_fornecedor, numero_documento, tipo_documento_id,
            data_emissao, valor_documento, valor_glosa, valor_liquido, ano_competencia, mes_competencia,
            parcela, lote_id, cadastro_interno_id
        )
    """)
    con.execute("""
        CREATE TABLE refined.deputados AS
        SELECT '101' AS deputado_id, 'Dep Alfa' AS nome_parlamentar, 'ALFA' AS nome_civil,
               56 AS legislatura_inicial_id, 57 AS legislatura_final_id, 'F' AS sexo,
               DATE '1980-01-01' AS data_nascimento, CAST(NULL AS DATE) AS data_falecimento,
               'SP' AS uf_nascimento, 'São Paulo' AS municipio_nascimento
    """)
    # Mesmo fornecedor 01234567000199 aparece DUAS vezes no CEIS (2 sanções distintas)
    # O mart 03 e o mart 07 NÃO podem multiplicar os R$ 900,00 por 2!
    con.execute("""
        CREATE TABLE refined.sancoes_ceis AS
        SELECT * FROM (
            VALUES
            ('S1', 'J', '01234567000199', 'Forn Punido', 'Forn Punido', 'Suspensão',
             DATE '2025-01-01', DATE '2025-12-31', DATE '2025-01-02', 'Nacional', 'CGU', 'DF', 'Federal'),
            ('S2', 'J', '01234567000199', 'Forn Punido', 'Forn Punido', 'Inidoneidade',
             DATE '2025-03-01', CAST(NULL AS DATE), DATE '2025-03-02', 'Nacional', 'TCU', 'DF', 'Federal')
        ) AS t(
            sancao_id, tipo_pessoa, documento_sancionado, nome_sancionado, razao_social_receita,
            categoria_sancao, data_inicio_sancao, data_fim_sancao, data_publicacao,
            abrangencia_sancao, orgao_sancionador, uf_orgao_sancionador, esfera_orgao_sancionador
        )
    """)
    con.execute("""
        CREATE TABLE refined.cotas_uf AS
        SELECT 35 AS codigo_ibge, 'SP' AS uf, 'São Paulo' AS nome_estado,
               'Sudeste' AS regiao, DECIMAL '41150.25' AS limite_mensal_cota
    """)


def test_marts_reais_excluem_negativo_e_nao_multiplicam_sancao_dupla(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    banco = tmp_path / "teste.duckdb"
    monkeypatch.setattr(db, "CAMINHO_BANCO", banco)

    con = db.conectar()
    try:
        _criar_refined_sintetico(con)
    finally:
        con.close()

    total_linhas = marts.executar_marts()
    assert total_linhas > 0

    con = db.conectar()
    try:
        despesa_m01 = con.execute("SELECT sum(despesa_liquida) FROM marts.gastos_mensais").fetchall()[0][0]
        ceis_row = con.execute(
            "SELECT total_lancamentos, lancamentos_ceis, despesa_total, despesa_sancao_vigente FROM marts.conformidade_ceis"
        ).fetchall()[0]
    finally:
        con.close()

    # R$ 900 + R$ 300 = R$ 1.200 (o lançamento negativo de -500 ficou de fora)
    assert despesa_m01 == Decimal("1200.00")
    assert ceis_row[0] == 2
    # O fornecedor punido tem 2 sanções no CEIS, mas a nota de R$ 900 conta apenas 1 vez!
    assert ceis_row[1] == 1
    assert ceis_row[2] == Decimal("1200.00")
    assert ceis_row[3] == Decimal("900.00")


def test_mart_apagado_desaparece_e_mart_vazio_faz_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    banco = tmp_path / "teste.duckdb"
    pasta_marts = tmp_path / "sql_marts"
    pasta_marts.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(db, "CAMINHO_BANCO", banco)
    monkeypatch.setattr(marts, "PASTA_MARTS", pasta_marts)

    con = db.conectar()
    try:
        _criar_refined_sintetico(con)
    finally:
        con.close()

    arq_00 = pasta_marts / "00_teste.sql"
    arq_01 = pasta_marts / "01_fixo.sql"
    arq_00.write_text("SELECT 1 AS x;", encoding="utf-8")
    arq_01.write_text("SELECT 2 AS y;", encoding="utf-8")

    marts.executar_marts()

    # Apaga 00_teste.sql: na próxima execução marts.teste deve sumir
    arq_00.unlink()
    marts.executar_marts()

    con = db.conectar()
    try:
        tabelas = {
            r[0]
            for r in con.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'marts'"
            ).fetchall()
        }
    finally:
        con.close()
    assert tabelas == {"fixo"}

    # Agora adiciona um mart vazio: deve falhar e fazer ROLLBACK mantendo marts.fixo intacto
    (pasta_marts / "02_vazio.sql").write_text("SELECT 1 AS z WHERE 1 = 0", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        marts.executar_marts()
    assert exc.value.code == 1

    con = db.conectar()
    try:
        val_fixo = con.execute("SELECT y FROM marts.fixo").fetchall()[0][0]
    finally:
        con.close()
    assert val_fixo == 2


def test_arquivo_sem_prefixo_para_antes_de_executar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pasta_marts = tmp_path / "sql_invalido"
    pasta_marts.mkdir(parents=True, exist_ok=True)
    (pasta_marts / "teste_sem_prefixo.sql").write_text("SELECT 1", encoding="utf-8")
    monkeypatch.setattr(marts, "PASTA_MARTS", pasta_marts)

    with pytest.raises(SystemExit) as exc:
        marts.executar_marts()
    assert exc.value.code == 1
