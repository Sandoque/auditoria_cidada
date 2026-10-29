"""Testes unitários de `painel.py`, `relatorio.py` e `pipeline/qualidade.py`."""

from pathlib import Path

import duckdb
import pandas as pd
import pytest

import painel
import relatorio
from pipeline import db, marts, qualidade


def _popular_refined_sintetico(con: duckdb.DuckDBPyConnection) -> None:
    db.criar_schema(con, "refined")
    con.execute("""
        CREATE TABLE refined.despesas_ceap AS
        SELECT * FROM (
            VALUES
            -- Lançamento 1: Dep 101 em SP, fornecedor sancionado durante vigência
            ('1', 'Dep Alfa', '101', 'SP', 'PA', 57, 1, 'DIVULGACAO', 'Forn Punido', '01234567000199', 'NF1', 0,
             TIMESTAMP '2025-05-10 10:00:00', DECIMAL '1000.00', DECIMAL '100.00', DECIMAL '900.00', 2025, 5, 0, 1, 1),
            -- Lançamento 2: Dep 101 em SP, fornecedor limpo
            ('2', 'Dep Alfa', '101', 'SP', 'PA', 57, 2, 'COMBUSTIVEL', 'Posto Limpo', '99888777000166', 'NF2', 0,
             TIMESTAMP '2025-05-12 12:00:00', DECIMAL '300.00', DECIMAL '0.00', DECIMAL '300.00', 2025, 5, 0, 1, 1)
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
    con.execute("""
        CREATE TABLE refined.sancoes_ceis AS
        SELECT 'S1' AS sancao_id, 'J' AS tipo_pessoa, '01234567000199' AS documento_sancionado,
               'Forn Punido' AS nome_sancionado, 'Forn Punido' AS razao_social_receita,
               'Suspensão' AS categoria_sancao, DATE '2025-01-01' AS data_inicio_sancao,
               DATE '2025-12-31' AS data_fim_sancao, DATE '2025-01-02' AS data_publicacao,
               'Nacional' AS abrangencia_sancao, 'CGU' AS orgao_sancionador,
               'DF' AS uf_orgao_sancionador, 'Federal' AS esfera_orgao_sancionador
    """)
    con.execute("""
        CREATE TABLE refined.cotas_uf AS
        SELECT 35 AS codigo_ibge, 'SP' AS uf, 'São Paulo' AS nome_estado,
               'Sudeste' AS regiao, DECIMAL '41150.25' AS limite_mensal_cota
    """)


def test_formatadores_puros_independem_de_locale() -> None:
    assert painel.reais(1003862.14) == "R$ 1.003.862,14"
    assert painel.reais(240.04, casas=2) == "R$ 240,04"
    assert painel.pct(93.2, casas=1) == "93,2%"
    assert painel.pct(0.47, casas=2) == "0,47%"
    assert painel.numero(96470, casas=0) == "96.470"
    assert painel.reais_compacto(3456789.0) == "R$ 3,46 mi"
    assert painel.reais_compacto(12345.0) == "R$ 12,3 mil"
    assert painel.reais_compacto(840.0) == "R$ 840,00"


def test_cartoes_separam_alcance_federal_e_so_ele_fica_em_alerta() -> None:
    # Linha de kpis inventada: 3 notas federais em 2 fornecedores; o resto da sanção vigente é restrita/sem info
    kpi = pd.Series({
        "despesa_total_reais": 2500000.0,
        "ticket_medio_nota": 500.0,
        "ticket_mediana_nota": 120.0,
        "pct_glosado": 1.5,
        "valor_glosado_total": 37500.0,
        "pct_teto_utilizado_geral": 76.3,
        "deputados_com_teto": 40,
        "deputados_acima_90_teto": 3,
        "pct_valor_regular": 98.0,
        "despesa_fornecedores_ceis": 50000.0,
        "despesa_sancao_vigente": 9000.0,
        "despesa_sancao_vigente_federal": 1000.0,
        "despesa_sancao_vigente_sem_info": 3000.0,
        "despesa_sancao_vigente_restrita": 5000.0,
        "lancamentos_sancao_vigente_federal": 3,
        "fornecedores_sancao_vigente_federal": 2,
    })
    lista = painel.cartoes(kpi)

    assert len(lista) == 7
    assert [c.alerta for c in lista] == [False] * 6 + [True]
    assert lista[0].valor == "R$ 2,50 mi"
    assert lista[3].valor == "76,3%"
    assert lista[3].detalhe == "3 de 40 deputados usaram 90% ou mais"
    assert lista[5].valor == "R$ 9.000,00"
    assert lista[5].detalhe == "Restrita: R$ 5,0 mil · sem info: R$ 3,0 mil"
    assert lista[6].valor == "R$ 1.000,00"
    assert lista[6].detalhe == "3 notas · 2 fornecedores"

    html = painel.html_cartoes([painel.Cartao("A < B", "1", "x & y", alerta=True)])
    assert html.count('class="card card-alert"') == 1
    assert "A &lt; B" in html and "x &amp; y" in html


def test_tabela_deputados_filtra_ordena_e_busca_sem_acento() -> None:
    # Três deputados inventados: dois no RJ, dois do PA, um nome acentuado e outro com prefixo parecido
    ranking = pd.DataFrame({
        "deputado_id": ["1", "2", "3"],
        "nome_parlamentar": ["João Alfa", "Maria Beta", "Joana Gama"],
        "partido": ["PA", "PB", "PA"],
        "uf": ["SP", "RJ", "RJ"],
        "meses_exercicio": [12, 3, 12],
        "despesa_liquida": [1000.0, 2000.0, 3000.0],
        "pct_teto_utilizado": [80.0, 95.5, 40.0],
        "fornecedores_distintos": [5, 2, 9],
        "maior_fornecedor": ["Forn X", "Forn Y", "Forn Z"],
        "pct_maior_fornecedor": [30.0, 90.0, 15.0],
        "posicao_maior_gasto": [3, 2, 1],
    })

    tabela = painel.tabela_deputados(ranking)
    assert list(tabela.columns) == list(painel.COLUNAS_TABELA_DEPUTADOS.values())
    assert list(tabela["Deputado"]) == ["Maria Beta", "João Alfa", "Joana Gama"]

    assert list(painel.tabela_deputados(ranking, nome="  joao ")["Deputado"]) == ["João Alfa"]
    assert list(painel.tabela_deputados(ranking, nome="JOA")["Deputado"]) == ["João Alfa", "Joana Gama"]
    assert list(painel.tabela_deputados(ranking, uf="RJ", partido="PA")["Deputado"]) == ["Joana Gama"]

    vazia = painel.tabela_deputados(ranking, uf="SP", nome="maria")
    assert vazia.empty
    assert list(vazia.columns) == list(painel.COLUNAS_TABELA_DEPUTADOS.values())


def test_painel_e_relatorio_sobre_banco_sintetico(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    banco = tmp_path / "sintetico.duckdb"
    monkeypatch.setattr(db, "CAMINHO_BANCO", banco)
    monkeypatch.setattr(painel, "CAMINHO_BANCO", banco)

    con = db.conectar()
    try:
        _popular_refined_sintetico(con)
        db.criar_schema(con, "raw")
        con.execute("CREATE TABLE raw.despesas_ceap AS SELECT * FROM refined.despesas_ceap")
    finally:
        con.close()

    marts.executar_marts()
    dados = painel.ler()

    assert set(dados.keys()) == set(painel.MARTS_PAINEL)
    assert len(painel.grafico_gastos_mensais(dados["gastos_mensais"]).data[0].x) == len(dados["gastos_mensais"])
    assert len(painel.grafico_categorias(dados["gastos_por_categoria"]).data[0].x) == len(dados["gastos_por_categoria"])
    assert len(painel.grafico_partidos(dados["gastos_por_partido"]).data[0].x) == len(dados["gastos_por_partido"])
    assert len(painel.grafico_gasto_uf(dados["gasto_medio_por_uf"]).data[0].x) == len(dados["gasto_medio_por_uf"])
    fig_ceis = painel.grafico_fornecedores_ceis(dados["fornecedores_sancionados"])
    em_vigencia = dados["fornecedores_sancionados"]["valor_recebido_em_vigencia"] > 0
    assert sum(len(trace.x) for trace in fig_ceis.data) == int(em_vigencia.sum())
    # A sanção sintética tem abrangência 'Nacional', fora do domínio conhecido: cai em sem informação
    assert [trace.name for trace in fig_ceis.data] == ["Vigente · alcance sem informação"]
    assert fig_ceis.layout.title.subtitle.text == "Maior: FORN PUNIDO · R$ 900,00 · alcance sem informação"

    fig_glosa = painel.grafico_glosas(dados["glosa_por_categoria"])
    assert sorted(fig_glosa.data[0].x) == sorted(dados["glosa_por_categoria"]["pct_valor_glosado"])
    assert fig_glosa.layout.title.subtitle.text.startswith("Maior taxa: DIVULGACAO (10,0%)")

    # R$ 900 de R$ 1.200: a 1ª posição acumula 75%, a 2ª cruza os 80%
    fig_pareto = painel.grafico_pareto_fornecedores(dados["fornecedores_pareto"])
    assert len(fig_pareto.data[0].x) == len(dados["fornecedores_pareto"])
    assert fig_pareto.layout.annotations[0].text == "<b>80% da despesa (pos. 2)</b>"
    assert fig_pareto.layout.title.subtitle.text == "80% da despesa está em 2 de 2 fornecedores"

    arq_html_1 = tmp_path / "rel1.html"
    arq_html_2 = tmp_path / "rel2.html"
    relatorio.gerar_relatorio(arq_html_1)
    relatorio.gerar_relatorio(arq_html_2)

    assert list(painel.grafico_gasto_uf(dados["gasto_medio_por_uf"]).data[0].x) == list(
        dados["gasto_medio_por_uf"]["pct_teto_utilizado"]
    )

    assert arq_html_1.is_file()
    assert arq_html_1.stat().st_size < 200 * 1024
    pagina = arq_html_1.read_text(encoding="utf-8")
    # A Faixa 2 traz o deputado sintético já renderizado (funciona sem JS) e o script dos filtros
    assert "<tr><td>Dep Alfa<td>PA<td>SP<td>1<td>R$ 1.200,00<td>" in pagina
    assert 'id="f-uf"' in pagina and "function filtrar()" in pagina
    linhas_1 = [ln for ln in arq_html_1.read_text(encoding="utf-8").splitlines() if "<footer>" not in ln]
    linhas_2 = [ln for ln in arq_html_2.read_text(encoding="utf-8").splitlines() if "<footer>" not in ln]
    assert linhas_1 == linhas_2


def test_qualidade_detecta_quebra_de_reconciliacao(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    banco = tmp_path / "qualidade.duckdb"
    monkeypatch.setattr(db, "CAMINHO_BANCO", banco)

    con = db.conectar()
    try:
        _popular_refined_sintetico(con)
        db.criar_schema(con, "raw")
        con.execute("CREATE TABLE raw.despesas_ceap AS SELECT * FROM refined.despesas_ceap")
    finally:
        con.close()

    marts.executar_marts()
    with pytest.raises(SystemExit) as exc:
        qualidade.executar_qualidade()
    assert exc.value.code == 1
