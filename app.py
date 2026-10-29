"""Aplicação Streamlit do painel de Auditoria Cidadã e Compliance.

Execução:
    uv run streamlit run app.py

Regra central: este arquivo não calcula nenhum indicador; apenas lê os DataFrames
prontos via painel.ler(), desenha os cartões de painel.cartoes(), a tabela de
painel.tabela_deputados() e as figuras Plotly em 5 faixas.

Deploy (Streamlit Community Cloud): o auditoria.duckdb não é versionado. Se ele não
existir, garantir_banco() roda ingestão, transformação e marts a partir de raw/ uma
única vez por servidor; localmente, com o banco já gerado, não faz nada.
"""

import importlib

import pandas as pd
import streamlit as st

import painel

st.set_page_config(
    page_title="Auditoria Cidadã · CEAP × CEIS",
    layout="wide",
)

_CSS_ALTO_CONTRASTE = """
<style>
  .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
    background-color: #F4F6F4 !important;
    color: #0B1315 !important;
  }
  h1, h2, h3, p, span, label, [data-testid="stMarkdownContainer"] p {
    color: #0B1315 !important;
  }
  [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {
    color: #1E293B !important;
    font-weight: 500 !important;
    opacity: 1 !important;
  }
  .stButton > button {
    background-color: #1A6B52 !important;
    color: #FFFFFF !important;
    border: 1px solid #134E3B !important;
    font-weight: 600 !important;
  }
  .stButton > button p, .stButton > button span {
    color: #FFFFFF !important;
  }
</style>
"""


@st.cache_resource(show_spinner="Montando o banco a partir de raw/ (só na primeira visita, 1 a 2 minutos)...")
def garantir_banco() -> None:
    if painel.CAMINHO_BANCO.is_file():
        return
    from pipeline import ingestao, marts, transformacao

    ingestao.executar_ingestao()
    transformacao.executar_transformacao()
    marts.executar_marts()


@st.cache_data
def carregar_dados() -> dict[str, pd.DataFrame]:
    garantir_banco()
    return painel.ler()


def renderizar_pagina() -> None:
    importlib.reload(painel)
    st.markdown(_CSS_ALTO_CONTRASTE, unsafe_allow_html=True)
    st.markdown(f"<style>{painel.CSS_CARTOES}</style>", unsafe_allow_html=True)

    col_titulo, col_ano, col_botao = st.columns([4, 1, 1])
    with col_botao:
        if st.button("Recarregar dados", width="stretch"):
            st.cache_data.clear()

    try:
        dados_todos = carregar_dados()
        anos = painel.anos(dados_todos)
        ano = col_ano.selectbox("Ano", anos)
        dados = painel.do_ano(dados_todos, ano)
        cartoes = painel.cartoes(dados["kpis"].iloc[0])
    except KeyError as exc:
        st.error(
            f"A coluna {exc} não existe nos marts: o banco foi gerado por uma versão "
            "anterior do pipeline.\n\nExecute no terminal `uv run python executar.py` "
            "e clique em **Recarregar dados**."
        )
        st.stop()
        return
    except (FileNotFoundError, LookupError) as exc:
        st.error(
            f"{exc}\n\nPara gerar os marts, execute no terminal:\n"
            "`uv run python -m pipeline.marts`"
        )
        st.stop()
        return

    periodo = painel.periodo(dados)
    with col_titulo:
        st.title(f"Auditoria Cidadã · Cota Parlamentar (CEAP {ano}) × Sanções CEIS/CGU")
        st.caption(painel.texto_periodo(periodo))
    if periodo.parcial:
        st.info(painel.AVISO_ANO_PARCIAL)

    # Faixa 1: Sete cartões executivos (lidos diretamente de marts.kpis)
    st.markdown(painel.html_cartoes(cartoes), unsafe_allow_html=True)

    # Faixa 2: Largura inteira — uso da cota por deputado (só filtra e ordena marts.ranking_deputados)
    st.subheader("Uso da cota por deputado")
    ranking = dados["ranking_deputados"]
    col_uf, col_partido, col_nome = st.columns([1, 1, 2])
    uf = col_uf.selectbox("UF", ["Todas", *sorted(ranking["uf"].dropna().unique())])
    partido = col_partido.selectbox("Partido", ["Todos", *sorted(ranking["partido"].dropna().unique())])
    nome = col_nome.text_input("Nome do deputado", placeholder="Digite parte do nome, com ou sem acento")
    tabela = painel.tabela_deputados(
        ranking,
        uf=None if uf == "Todas" else uf,
        partido=None if partido == "Todos" else partido,
        nome=nome,
    )
    st.dataframe(
        tabela,
        hide_index=True,
        height=420,
        width="stretch",
        column_config={
            "% do teto": st.column_config.ProgressColumn(
                format="%.1f%%", min_value=0, max_value=100, color="#1A6B52"
            ),
            "Meses": st.column_config.NumberColumn(format="%.1f"),
            "Gasto (R$)": st.column_config.NumberColumn(format="localized"),
            "% no maior fornecedor": st.column_config.NumberColumn(format="%.1f%%"),
        },
    )
    st.caption(f"{painel.numero(len(tabela))} deputados exibidos · {painel.NOTA_TETO}")

    # Faixa 3: Três colunas iguais — Quem usa a cota e onde vai o dinheiro?
    f3_col1, f3_col2, f3_col3 = st.columns(3)
    with f3_col1:
        st.plotly_chart(
            painel.grafico_gasto_uf(dados["gasto_medio_por_uf"]),
            width="stretch",
            theme=None,
        )
    with f3_col2:
        st.plotly_chart(
            painel.grafico_partidos(dados["gastos_por_partido"]),
            width="stretch",
            theme=None,
        )
    with f3_col3:
        st.plotly_chart(
            painel.grafico_categorias(dados["gastos_por_categoria"]),
            width="stretch",
            theme=None,
        )

    # Faixa 4: Três colunas iguais — Onde mora o risco e a concentração?
    f4_col1, f4_col2, f4_col3 = st.columns(3)
    with f4_col1:
        st.plotly_chart(
            painel.grafico_fornecedores_ceis(dados["fornecedores_sancionados"]),
            width="stretch",
            theme=None,
        )
    with f4_col2:
        st.plotly_chart(
            painel.grafico_glosas(dados["glosa_por_categoria"]),
            width="stretch",
            theme=None,
        )
    with f4_col3:
        st.plotly_chart(
            painel.grafico_pareto_fornecedores(dados["fornecedores_pareto"]),
            width="stretch",
            theme=None,
        )

    # Faixa 5: Duas colunas compactas — ritmo mensal e divulgação no período eleitoral (compara com o ano anterior)
    f5_col1, f5_col2 = st.columns(2)
    with f5_col1:
        st.plotly_chart(
            painel.grafico_gastos_mensais(dados["gastos_mensais"], parcial=periodo.parcial),
            width="stretch",
            theme=None,
        )
    with f5_col2:
        st.plotly_chart(
            painel.grafico_divulgacao_eleitoral(dados_todos["divulgacao_eleitoral"], ano),
            width="stretch",
            theme=None,
        )


if __name__ == "__main__":
    renderizar_pagina()
