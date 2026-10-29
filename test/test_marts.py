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
        SELECT 35 AS codigo_ibge, 'SP' AS uf, 'São Paulo' AS nome_estado, 'Sudeste' AS regiao
    """)
    con.execute("""
        CREATE TABLE refined.limites_cota_uf AS
        SELECT 'SP' AS uf, DATE '2023-02-01' AS vigencia_inicio,
               DECIMAL '41150.25' AS limite_mensal_cota, '270/2023' AS ato_da_mesa
    """)
    # Histórico vazio: sem período oficial, o teto cai na reserva aproximada (meses com despesa)
    con.execute("""
        CREATE TABLE refined.historico_deputados (
            deputado_id VARCHAR, data_hora TIMESTAMP, situacao VARCHAR, condicao_eleitoral VARCHAR,
            descricao_status VARCHAR, partido VARCHAR, uf VARCHAR, legislatura_id INTEGER, nome_parlamentar VARCHAR
        )
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


def _trocar_por_cenario_de_alcance(con: duckdb.DuckDBPyConnection) -> None:
    # Valores em potências de 2: cada soma esperada só fecha com um único conjunto de notas.
    con.execute("""
        CREATE OR REPLACE TABLE refined.despesas_ceap AS
        SELECT * FROM (
            VALUES
            -- N1: fornecedor A com duas sanções vigentes (restrita e federal) — vale a federal, conta 1 vez
            ('1', 'Dep Alfa', '101', 'SP', 'PA', 57, 1, 'DIVULGACAO', 'Forn A', '11111111000111', 'NF1', 0,
             TIMESTAMP '2025-05-10 10:00:00', DECIMAL '100.00', DECIMAL '0.00', DECIMAL '100.00', 2025, 5, 0, 1, 1),
            -- N2: fornecedor B com sanção vigente 'Sem Informação' — cai em sem_info
            ('2', 'Dep Alfa', '101', 'SP', 'PA', 57, 1, 'DIVULGACAO', 'Forn B', '22222222000122', 'NF2', 0,
             TIMESTAMP '2025-05-10 10:00:00', DECIMAL '200.00', DECIMAL '0.00', DECIMAL '200.00', 2025, 5, 0, 1, 1),
            -- N3: fornecedor C com sanção vigente só na esfera municipal — cai em restrita
            ('3', 'Dep Alfa', '101', 'SP', 'PA', 57, 1, 'DIVULGACAO', 'Forn C', '33333333000133', 'NF3', 0,
             TIMESTAMP '2025-05-10 10:00:00', DECIMAL '400.00', DECIMAL '0.00', DECIMAL '400.00', 2025, 5, 0, 1, 1),
            -- N4: fornecedor D emitida no intervalo ENTRE duas sanções — o envelope min/max marcaria vigente
            ('4', 'Dep Alfa', '101', 'SP', 'PA', 57, 1, 'DIVULGACAO', 'Forn D', '44444444000144', 'NF4', 0,
             TIMESTAMP '2025-05-10 10:00:00', DECIMAL '800.00', DECIMAL '0.00', DECIMAL '800.00', 2025, 5, 0, 1, 1),
            -- N5: fornecedor E fora do CEIS — limpo
            ('5', 'Dep Alfa', '101', 'SP', 'PA', 57, 1, 'DIVULGACAO', 'Forn E', '55555555000155', 'NF5', 0,
             TIMESTAMP '2025-05-10 10:00:00', DECIMAL '1600.00', DECIMAL '0.00', DECIMAL '1600.00', 2025, 5, 0, 1, 1),
            -- N6: fornecedor C de novo, depois do fim da sanção — no CEIS, mas fora da vigência
            ('6', 'Dep Alfa', '101', 'SP', 'PA', 57, 1, 'DIVULGACAO', 'Forn C', '33333333000133', 'NF6', 0,
             TIMESTAMP '2025-09-10 10:00:00', DECIMAL '3200.00', DECIMAL '0.00', DECIMAL '3200.00', 2025, 9, 0, 1, 1)
        ) AS t(
            documento_id, nome_parlamentar, deputado_id, uf, partido, legislatura_id, subcota_id,
            categoria_despesa, nome_fornecedor, documento_fornecedor, numero_documento, tipo_documento_id,
            data_emissao, valor_documento, valor_glosa, valor_liquido, ano_competencia, mes_competencia,
            parcela, lote_id, cadastro_interno_id
        )
    """)
    con.execute("""
        CREATE OR REPLACE TABLE refined.sancoes_ceis AS
        SELECT * FROM (
            VALUES
            -- A: restrita ao órgão federal (nível 1) e todas as esferas (nível 3), ambas vigentes em N1
            ('A1', 'J', '11111111000111', 'Forn A', 'Forn A', 'Suspensão', DATE '2025-01-01', DATE '2025-12-31',
             DATE '2025-01-02', 'No órgão sancionador', 'Ministério X', 'DF', 'FEDERAL'),
            ('A2', 'J', '11111111000111', 'Forn A', 'Forn A', 'Impedimento', DATE '2025-02-01', CAST(NULL AS DATE),
             DATE '2025-02-02', 'Todas as Esferas em todos os Poderes', 'Prefeitura Y', 'SP', 'MUNICIPAL'),
            -- B: abrangência sem informação no cadastro
            ('B1', 'J', '22222222000122', 'Forn B', 'Forn B', 'Inidoneidade', DATE '2025-01-01', DATE '2025-12-31',
             DATE '2025-01-02', 'Sem Informação', 'Secretaria Z', 'MG', 'ESTADUAL'),
            -- C: todos os Poderes, mas só da esfera municipal; termina antes da nota N6
            ('C1', 'J', '33333333000133', 'Forn C', 'Forn C', 'Impedimento', DATE '2025-01-01', DATE '2025-06-30',
             DATE '2025-01-02', 'Em todos os Poderes da Esfera do órgão sancionador', 'Prefeitura W', 'RS', 'MUNICIPAL'),
            -- D: duas sanções federais amplas separadas por um intervalo que contém a nota N4
            ('D1', 'J', '44444444000144', 'Forn D', 'Forn D', 'Suspensão', DATE '2023-01-01', DATE '2023-12-31',
             DATE '2023-01-02', 'Todas as Esferas em todos os Poderes', 'CGU', 'DF', 'FEDERAL'),
            ('D2', 'J', '44444444000144', 'Forn D', 'Forn D', 'Suspensão', DATE '2026-01-01', CAST(NULL AS DATE),
             DATE '2026-01-02', 'Todas as Esferas em todos os Poderes', 'CGU', 'DF', 'FEDERAL')
        ) AS t(
            sancao_id, tipo_pessoa, documento_sancionado, nome_sancionado, razao_social_receita,
            categoria_sancao, data_inicio_sancao, data_fim_sancao, data_publicacao,
            abrangencia_sancao, orgao_sancionador, uf_orgao_sancionador, esfera_orgao_sancionador
        )
    """)


def test_marts_classificam_alcance_da_sancao_vigente_por_sancao(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    banco = tmp_path / "alcance.duckdb"
    monkeypatch.setattr(db, "CAMINHO_BANCO", banco)

    con = db.conectar()
    try:
        _criar_refined_sintetico(con)
        _trocar_por_cenario_de_alcance(con)
    finally:
        con.close()

    marts.executar_marts()

    con = db.conectar()
    try:
        m03 = con.execute("""
            SELECT lancamentos_limpos, lancamentos_ceis, lancamentos_sancao_vigente,
                   lancamentos_sancao_vigente_federal, lancamentos_sancao_vigente_sem_info,
                   lancamentos_sancao_vigente_restrita, despesa_fornecedores_ceis, despesa_sancao_vigente,
                   despesa_sancao_vigente_federal, despesa_sancao_vigente_sem_info, despesa_sancao_vigente_restrita
            FROM marts.conformidade_ceis
        """).fetchall()[0]
        m11 = con.execute("""
            SELECT despesa_sancao_vigente, despesa_sancao_vigente_federal, despesa_sancao_vigente_sem_info,
                   despesa_sancao_vigente_restrita, lancamentos_sancao_vigente_federal,
                   fornecedores_sancao_vigente_federal
            FROM marts.kpis
        """).fetchall()[0]
        m07 = {
            linha[0]: linha[1:]
            for linha in con.execute("""
                SELECT nome_fornecedor, lancamentos, lancamentos_em_vigencia, valor_recebido_total,
                       valor_recebido_em_vigencia, alcance_sancao_vigente
                FROM marts.fornecedores_sancionados
            """).fetchall()
        }
    finally:
        con.close()

    # N5 limpa; N1, N2, N3, N4 e N6 no CEIS; só N1, N2 e N3 em vigência (N4 cai no intervalo, N6 depois do fim)
    assert m03[:3] == (1, 5, 3)
    assert m03[3:6] == (1, 1, 1)
    assert m03[6] == Decimal("4700.00")
    assert m03[7:] == (Decimal("700.00"), Decimal("100.00"), Decimal("200.00"), Decimal("400.00"))
    assert m11 == (Decimal("700.00"), Decimal("100.00"), Decimal("200.00"), Decimal("400.00"), 1, 1)

    assert m07["Forn A"] == (1, 1, Decimal("100.00"), Decimal("100.00"), "federal")
    assert m07["Forn B"] == (1, 1, Decimal("200.00"), Decimal("200.00"), "sem_informacao")
    assert m07["Forn C"] == (2, 1, Decimal("3600.00"), Decimal("400.00"), "restrita")
    assert m07["Forn D"] == (1, 0, Decimal("800.00"), Decimal("0.00"), None)


def _trocar_por_cenario_de_teto(con: duckdb.DuckDBPyConnection) -> None:
    # Limites redondos (SP R$ 1.000, RJ R$ 2.000) para o uso do teto ser conferível de cabeça.
    con.execute("""
        CREATE OR REPLACE TABLE refined.cotas_uf AS
        SELECT * FROM (
            VALUES (35, 'SP', 'São Paulo', 'Sudeste'), (33, 'RJ', 'Rio de Janeiro', 'Sudeste')
        ) AS t(codigo_ibge, uf, nome_estado, regiao)
    """)
    con.execute("""
        CREATE OR REPLACE TABLE refined.limites_cota_uf AS
        SELECT * FROM (
            VALUES ('SP', DATE '2023-02-01', DECIMAL '1000.00', '270/2023'),
                   ('RJ', DATE '2023-02-01', DECIMAL '2000.00', '270/2023')
        ) AS t(uf, vigencia_inicio, limite_mensal_cota, ato_da_mesa)
    """)
    con.execute("""
        CREATE OR REPLACE TABLE refined.historico_deputados AS
        SELECT * FROM (
            VALUES
            -- H1 a H3: Dep 102 entra em 01/01; a licença para tratamento de saúde NÃO fecha o período (art. 11, § 2º);
            -- a saída para Secretário de Estado fecha em 31/01, e o dia do afastamento conta — janeiro inteiro
            ('102', TIMESTAMP '2025-01-01 10:00:00', 'Exercício', 'Titular', 'Entrada - Posse de Eleito Titular',
             'PB', 'RJ', 57, 'Dep Beta'),
            ('102', TIMESTAMP '2025-01-10 10:00:00', 'Licença', 'Titular',
             'Saída - Afastamento com prazo determinado - Licença para Tratamento de Saúde', 'PB', 'RJ', 57, 'Dep Beta'),
            ('102', TIMESTAMP '2025-01-31 18:00:00', 'Licença', 'Titular',
             'Saída - Afastamento sem prazo determinado - Secretário de Estado', 'PB', 'RJ', 57, 'Dep Beta'),
            -- H4: evento informativo sem situação — não muda o estado
            ('103', TIMESTAMP '2023-02-01 00:00:00', NULL, NULL,
             'Nome no início da legislatura / Partido no início da legislatura', 'PB', 'RJ', 57, 'Dep Gama'),
            -- H5 e H6: Dep 103 reentra com descrição composta e situação CONVOCADO (como a API grava) e sai em 28/02:
            -- 14 dias de fevereiro = meio mês de cota
            ('103', TIMESTAMP '2025-02-15 09:00:00', 'CONVOCADO', 'Suplente',
             'DIVERSO - Alteração na Situação - Efetivação (Ato da Presidência) / Entrada - Reassunção',
             'PB', 'RJ', 57, 'Dep Gama'),
            ('103', TIMESTAMP '2025-02-28 10:00:00', 'SUPLENCIA', 'Suplente',
             'Saída - Afastamento sem prazo determinado - Afastamento de Suplente (automático)',
             'PB', 'RJ', 57, 'Dep Gama')
        ) AS t(deputado_id, data_hora, situacao, condicao_eleitoral, descricao_status, partido, uf, legislatura_id, nome_parlamentar)
    """)
    con.execute("""
        CREATE OR REPLACE TABLE refined.despesas_ceap AS
        SELECT * FROM (
            VALUES
            -- T1 e T2: Dep 101 (SP) sem histórico, despesa em março e maio — reserva de 3 meses (abril sem despesa conta)
            ('1', 'Dep Alfa', '101', 'SP', 'PA', 57, 1, 'DIVULGACAO', 'Forn X', '01234567000199', 'NF1', 0,
             TIMESTAMP '2025-03-10 10:00:00', DECIMAL '500.00', DECIMAL '0.00', DECIMAL '500.00', 2025, 3, 0, 1, 1),
            ('2', 'Dep Alfa', '101', 'SP', 'PA', 57, 1, 'DIVULGACAO', 'Forn Y', '99888777000166', 'NF2', 0,
             TIMESTAMP '2025-05-10 10:00:00', DECIMAL '1500.00', DECIMAL '0.00', DECIMAL '1500.00', 2025, 5, 0, 1, 1),
            -- T3: Dep 102 (RJ) gasta o dobro do teto do único mês em que exerceu — uso de 200%
            ('3', 'Dep Beta', '102', 'RJ', 'PB', 57, 1, 'DIVULGACAO', 'Forn X', '01234567000199', 'NF3', 0,
             TIMESTAMP '2025-01-10 10:00:00', DECIMAL '4000.00', DECIMAL '0.00', DECIMAL '4000.00', 2025, 1, 0, 1, 1),
            -- T4: Liderança (sem deputado, UF e partido) — fora de qualquer teto individual
            ('4', 'LIDERANÇA DO PA', NULL, NULL, NULL, 57, 1, 'DIVULGACAO', 'Forn Y', '99888777000166', 'NF4', 0,
             TIMESTAMP '2025-01-10 10:00:00', DECIMAL '800.00', DECIMAL '0.00', DECIMAL '800.00', 2025, 1, 0, 1, 1),
            -- T5 e T6: Dep 103 (RJ) divide R$ 600 igualmente entre X e Y — empate vai para o menor documento (X);
            -- teto de meio mês (R$ 1.000) — uso de 60%
            ('5', 'Dep Gama', '103', 'RJ', 'PB', 57, 1, 'DIVULGACAO', 'Forn Y', '99888777000166', 'NF5', 0,
             TIMESTAMP '2025-02-10 10:00:00', DECIMAL '300.00', DECIMAL '0.00', DECIMAL '300.00', 2025, 2, 0, 1, 1),
            ('6', 'Dep Gama', '103', 'RJ', 'PB', 57, 1, 'DIVULGACAO', 'Forn X', '01234567000199', 'NF6', 0,
             TIMESTAMP '2025-02-11 10:00:00', DECIMAL '300.00', DECIMAL '0.00', DECIMAL '300.00', 2025, 2, 0, 1, 1)
        ) AS t(
            documento_id, nome_parlamentar, deputado_id, uf, partido, legislatura_id, subcota_id,
            categoria_despesa, nome_fornecedor, documento_fornecedor, numero_documento, tipo_documento_id,
            data_emissao, valor_documento, valor_glosa, valor_liquido, ano_competencia, mes_competencia,
            parcela, lote_id, cadastro_interno_id
        )
    """)


def test_marts_medem_uso_do_teto_por_dias_de_exercicio_e_concentracao(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    banco = tmp_path / "teto.duckdb"
    monkeypatch.setattr(db, "CAMINHO_BANCO", banco)

    con = db.conectar()
    try:
        _criar_refined_sintetico(con)
        _trocar_por_cenario_de_teto(con)
    finally:
        con.close()

    marts.executar_marts()

    con = db.conectar()
    try:
        m04 = {
            linha[0]: linha[1:]
            for linha in con.execute("""
                SELECT deputado_id, meses_exercicio, pct_teto_utilizado, maior_fornecedor, pct_maior_fornecedor,
                       fonte_periodo
                FROM marts.ranking_deputados
            """).fetchall()
        }
        m06 = {
            linha[0]: linha[1:]
            for linha in con.execute(
                "SELECT uf, deputado_meses, pct_teto_utilizado FROM marts.gasto_medio_por_uf"
            ).fetchall()
        }
        m10 = dict(con.execute("SELECT partido, pct_teto_utilizado FROM marts.gastos_por_partido").fetchall())
        m11 = con.execute(
            "SELECT pct_teto_utilizado_geral, deputados_com_teto, deputados_acima_90_teto FROM marts.kpis"
        ).fetchall()[0]
    finally:
        con.close()

    # Percentuais e meses saem de round(..., 2) em DOUBLE; a comparação exata vale porque o literal é o mesmo double.
    # 101: R$ 2.000 em 3 meses de R$ 1.000 (reserva); 102: R$ 4.000 em janeiro de R$ 2.000;
    # 103: R$ 600 em 14 dias de fevereiro (R$ 1.000)
    assert m04["101"] == (3.0, 66.67, "Forn Y", 75.0, "aproximado")
    assert m04["102"] == (1.0, 200.0, "Forn X", 100.0, "oficial")
    assert m04["103"] == (0.5, 60.0, "Forn X", 50.0, "oficial")
    assert None not in m04

    # RJ soma antes de dividir: R$ 4.600 / (1,5 deputado-mês × R$ 2.000) = 153,33%, não a média de 200% e 60%
    assert m06 == {"SP": (3.0, 66.67), "RJ": (1.5, 153.33)}
    assert m10 == {"PA": 66.67, "PB": 153.33, "LIDERANCAS": None}
    # R$ 6.600 / R$ 6.000 de teto; só o 102 passa de 90%
    assert m11 == (110.0, 3, 1)


def test_marts_separam_anos_e_trocam_limite_no_meio_do_mes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    banco = tmp_path / "anos.duckdb"
    monkeypatch.setattr(db, "CAMINHO_BANCO", banco)

    con = db.conectar()
    try:
        _criar_refined_sintetico(con)
        # SP passa de R$ 1.000 para R$ 1.280 em 20/02/2026, como no reajuste do Ato da Mesa n. 244/2026
        con.execute("""
            CREATE OR REPLACE TABLE refined.limites_cota_uf AS
            SELECT * FROM (
                VALUES ('SP', DATE '2023-02-01', DECIMAL '1000.00', '270/2023'),
                       ('SP', DATE '2026-02-20', DECIMAL '1280.00', '244/2026')
            ) AS t(uf, vigencia_inicio, limite_mensal_cota, ato_da_mesa)
        """)
        # Dep 101 em exercício desde a posse da legislatura
        con.execute("""
            INSERT INTO refined.historico_deputados VALUES
            ('101', TIMESTAMP '2023-02-01 12:05:00', 'Exercício', 'Titular', 'Entrada - Posse de Eleito Titular',
             'PA', 'SP', 57, 'Dep Alfa')
        """)
        # Uma nota de fevereiro/2026 do Dep 101 a fornecedor limpo, além das notas de maio/2025 da base
        con.execute("""
            INSERT INTO refined.despesas_ceap VALUES
            ('7', 'Dep Alfa', '101', 'SP', 'PA', 57, 3, 'PASSAGEM', 'Cia Aerea', '99888777000166', 'NF7', 0,
             TIMESTAMP '2026-02-25 08:00:00', DECIMAL '2090.00', DECIMAL '0.00', DECIMAL '2090.00', 2026, 2, 0, 1, 1)
        """)
    finally:
        con.close()

    marts.executar_marts()

    con = db.conectar()
    try:
        teto = {
            (linha[0], linha[1]): linha[2:]
            for linha in con.execute("""
                SELECT ano, deputado_id, dias_exercicio, meses_exercicio, teto_periodo, pct_teto_utilizado, fonte_periodo
                FROM marts.teto_deputado_ano
            """).fetchall()
        }
        kpis = con.execute("SELECT ano, despesa_total_reais FROM marts.kpis ORDER BY ano").fetchall()
        posicoes = con.execute("SELECT ano, posicao_maior_gasto FROM marts.ranking_deputados ORDER BY ano").fetchall()
        pct_categorias = con.execute(
            "SELECT ano, sum(pct_total) FROM marts.gastos_por_categoria GROUP BY ano ORDER BY ano"
        ).fetchall()
    finally:
        con.close()

    # 2025 vai até maio (último mês com dados): 151 dias × R$ 1.000/mês = R$ 5.000 de teto para R$ 1.200 gastos
    assert teto[(2025, "101")] == (151, 5.0, 5000.0, 24.0, "oficial")
    # 2026 vai até fevereiro: janeiro R$ 1.000 + 19 dias a R$ 1.000/28 + 9 dias a R$ 1.280/28 = R$ 2.090
    assert teto[(2026, "101")] == (59, 2.0, 2090.0, 100.0, "oficial")
    assert kpis == [(2025, Decimal("1200.00")), (2026, Decimal("2090.00"))]
    # Ranking e percentuais recomeçam em cada ano
    assert posicoes == [(2025, 1), (2026, 1)]
    assert pct_categorias == [(2025, 100.0), (2026, 100.0)]


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
