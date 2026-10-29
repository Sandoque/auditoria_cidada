"""Aplicação Streamlit do painel de Auditoria Cidadã e Compliance.

Execução:
    uv run streamlit run app.py

Regra central: este arquivo não calcula nenhum indicador; apenas lê os DataFrames
prontos via painel.ler(), formata os cartões e exibe as figuras Plotly em 4 faixas.
"""

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
  [data-testid="stMetric"] {
    background-color: #FFFFFF !important;
    border: 1px solid #CBD5E1 !important;
    border-top: 4px solid #1A6B52 !important;
    border-radius: 8px !important;
    padding: 12px 14px !important;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.06) !important;
  }
  [data-testid="stMetricLabel"], [data-testid="stMetricLabel"] p, [data-testid="stMetricLabel"] div {
    color: #0F172A !important;
    font-weight: 600 !important;
    font-size: 0.82rem !important;
    line-height: 1.25 !important;
    white-space: normal !important;
    opacity: 1 !important;
  }
  [data-testid="stMetricValue"], [data-testid="stMetricValue"] div {
    color: #0B1315 !important;
    font-weight: 700 !important;
    font-size: 1.15rem !important;
  }
  [data-testid="stPlotlyChart"] {
    background-color: #FFFFFF !important;
    border: 1px solid #CBD5E1 !important;
    border-radius: 8px !important;
    padding: 6px !important;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.05) !important;
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


@st.cache_data
def carregar_dados() -> dict[str, pd.DataFrame]:
    return painel.ler()


def renderizar_pagina() -> None:
    st.markdown(_CSS_ALTO_CONTRASTE, unsafe_allow_html=True)

    col_titulo, col_botao = st.columns([5, 1])
    with col_titulo:
        st.title("Auditoria Cidadã · Cota Parlamentar (CEAP 2025) × Sanções CEIS/CGU")
    with col_botao:
        if st.button("Recarregar dados", width="stretch"):
            st.cache_data.clear()

    try:
        dados = carregar_dados()
    except (FileNotFoundError, LookupError) as exc:
        st.error(
            f"{exc}\n\nPara gerar os marts, execute no terminal:\n"
            "`uv run python -m pipeline.marts`"
        )
        st.stop()
        return

    df_mensal = dados["gastos_mensais"].sort_values("mes").copy()
    df_mensal["mes_str"] = pd.to_datetime(df_mensal["mes"]).dt.strftime("%Y-%m")
    opcoes_mes = df_mensal["mes_str"].tolist()

    if len(opcoes_mes) >= 2:
        inicio_sel, fim_sel = st.select_slider(
            "Filtro de período (mês de competência para a série temporal):",
            options=opcoes_mes,
            value=(opcoes_mes[0], opcoes_mes[-1]),
        )
        st.caption(
            "Nota: o filtro recorta a série mensal (01). Os cartões e demais gráficos valem para o período completo."
        )
        df_mensal_filtrado = df_mensal[
            (df_mensal["mes_str"] >= inicio_sel) & (df_mensal["mes_str"] <= fim_sel)
        ]
    else:
        df_mensal_filtrado = df_mensal

    # Faixa 1: Sete cartões executivos (lidos diretamente de marts.kpis)
    kpi = dados["kpis"].iloc[0]
    c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
    c1.metric(
        "Despesa líquida · válida",
        painel.reais(kpi["despesa_total_reais"]),
    )
    c2.metric(
        "Ticket médio · por nota",
        painel.reais(kpi["ticket_medio_nota"]),
    )
    c3.metric(
        "Taxa de glosa · % cortado",
        painel.pct(kpi["pct_glosado"], casas=2),
    )
    c4.metric(
        "Fornecedores recorrentes · 2+",
        painel.pct(kpi["pct_fornecedores_recorrentes"], casas=2),
    )
    c5.metric(
        "Valor regular · fora do CEIS",
        painel.pct(kpi["pct_valor_regular"], casas=2),
    )
    c6.metric(
        "Pago em sanção ativa · CEIS",
        painel.reais(kpi["despesa_sancao_vigente"]),
    )
    c7.metric(
        "Notas em sanção ativa · CEIS",
        painel.numero(kpi["lancamentos_sancao_vigente"], casas=0),
    )

    # Faixa 2: Largura inteira — evolução mensal
    st.plotly_chart(
        painel.grafico_gastos_mensais(df_mensal_filtrado),
        width="stretch",
        theme=None,
    )

    # Faixa 3: Três colunas iguais — Onde estão os gastos?
    f3_col1, f3_col2, f3_col3 = st.columns(3)
    with f3_col1:
        st.plotly_chart(
            painel.grafico_categorias(dados["gastos_por_categoria"]),
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
            painel.grafico_gasto_uf(dados["gasto_medio_por_uf"]),
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


if __name__ == "__main__":
    renderizar_pagina()
