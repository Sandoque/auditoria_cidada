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


@st.cache_data
def carregar_dados() -> dict[str, pd.DataFrame]:
    return painel.ler()


def renderizar_pagina() -> None:
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
    )

    # Faixa 3: Três colunas iguais — Onde estão os gastos?
    f3_col1, f3_col2, f3_col3 = st.columns(3)
    with f3_col1:
        st.plotly_chart(
            painel.grafico_categorias(dados["gastos_por_categoria"]),
            width="stretch",
        )
    with f3_col2:
        st.plotly_chart(
            painel.grafico_partidos(dados["gastos_por_partido"]),
            width="stretch",
        )
    with f3_col3:
        st.plotly_chart(
            painel.grafico_gasto_uf(dados["gasto_medio_por_uf"]),
            width="stretch",
        )

    # Faixa 4: Três colunas iguais — Onde mora o risco e a concentração?
    f4_col1, f4_col2, f4_col3 = st.columns(3)
    with f4_col1:
        st.plotly_chart(
            painel.grafico_fornecedores_ceis(dados["fornecedores_sancionados"]),
            width="stretch",
        )
    with f4_col2:
        st.plotly_chart(
            painel.grafico_glosas(dados["glosa_por_categoria"]),
            width="stretch",
        )
    with f4_col3:
        st.plotly_chart(
            painel.grafico_pareto_fornecedores(dados["fornecedores_pareto"]),
            width="stretch",
        )


if __name__ == "__main__":
    renderizar_pagina()
