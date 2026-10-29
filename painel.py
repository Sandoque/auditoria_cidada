"""Módulo de leitura de marts, formatação numérica e construção de gráficos Plotly.

SPEC DO MÓDULO (Fonte da Verdade):
1. LEITURA:
   ler(marts) abre auditoria.duckdb em modo read_only=True, executa apenas
   SELECT * FROM marts.<nome> para cada mart solicitado e fecha a conexão
   imediatamente antes de retornar o dicionário de DataFrames.
   Motivo: não bloquear o arquivo do banco enquanto o painel estiver aberto.

2. NENHUM CÁLCULO DE NEGÓCIO:
   Este módulo não realiza agregações, somas, médias ou junções de tabelas.
   Todo número exibido já vem pronto do respectivo mart em SQL. Permitido apenas
   filtrar linhas, ordenar, recortar head(n) e formatar strings.

3. FORMATAÇÃO PURA:
   reais(valor, casas=2), pct(valor, casas=1) e numero(valor, casas=0) formatam
   valores no padrão brasileiro (ponto para milhar e vírgula para decimal) sem
   depender do locale do sistema operacional.

4. SEPARAÇÃO:
   Este módulo não importa streamlit, permitindo que app.py e relatorio.py
   compartilhem exatamente os mesmos dados, formatações e figuras Plotly.
"""

import re
from collections.abc import Iterable
from pathlib import Path

import duckdb
import pandas as pd
import plotly.graph_objects as go

CAMINHO_BANCO = Path(__file__).resolve().parent / "auditoria.duckdb"
_IDENTIFICADOR_VALIDO = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

MARTS_PAINEL: tuple[str, ...] = (
    "gastos_mensais",
    "gastos_por_categoria",
    "conformidade_ceis",
    "ranking_deputados",
    "recorrencia_fornecedores",
    "gasto_medio_por_uf",
    "fornecedores_sancionados",
    "glosa_por_categoria",
    "fornecedores_pareto",
    "gastos_por_partido",
    "kpis",
    "deputados_por_uf",
)

COR_PRINCIPAL = "#1A6B52"
COR_DESTAQUE = "#B85C00"
COR_GRADE = "#CBD5E1"
COR_TEXTO = "#0B1315"
COR_EIXO = "#1E293B"
FONTE_PADRAO = "Segoe UI, Arial, sans-serif"

_MAPA_CATEGORIAS: dict[str, str] = {
    "DIVULGAÇÃO DA ATIVIDADE PARLAMENTAR": "Divulgação Parlamentar",
    "LOCAÇÃO OU FRETAMENTO DE VEÍCULOS AUTOMOTORES": "Locação de Veículos",
    "MANUTENÇÃO DE ESCRITÓRIO DE APOIO À ATIVIDADE PARLAMENTAR": "Manutenção Escritório",
    "COMBUSTÍVEIS E LUBRIFICANTES": "Combustíveis e Lubrif.",
    "HOSPEDAGEM ,EXCETO DO PARLAMENTAR NO DISTRITO FEDERAL": "Hospedagem (fora DF)",
    "TELEFONIA": "Telefonia",
    "LOCAÇÃO OU FRETAMENTO DE AERONAVES": "Locação de Aeronaves",
    "FORNECIMENTO DE ALIMENTAÇÃO DO PARLAMENTAR": "Alimentação",
    "SERVIÇO DE SEGURANÇA PRESTADO POR EMPRESA ESPECIALIZADA": "Serviço de Segurança",
    "SERVIÇO DE TÁXI, PEDÁGIO E ESTACIONAMENTO": "Táxi, Pedágio e Estac.",
    "PASSAGEM AÉREA - REEMBOLSO": "Passagem Aérea (Reemb.)",
    "PASSAGEM AÉREA - RPA": "Passagem Aérea (RPA)",
    "LOCAÇÃO OU FRETAMENTO DE EMBARCAÇÕES": "Locação Embarcações",
    "PASSAGENS TERRESTRES, MARÍTIMAS OU FLUVIAIS": "Passagens Terrestres",
    "SERVIÇOS POSTAIS": "Serviços Postais",
    "ASSINATURA DE PUBLICAÇÕES": "Assinatura Publicações",
    "PARTICIPAÇÃO EM CURSO, PALESTRA OU EVENTO SIMILAR": "Cursos e Palestras",
    "AQUISIÇÃO DE TOKENS E CERTIFICADOS DIGITAIS": "Certificados Digitais",
}


def _rotulo_categoria(nome: object) -> str:
    chave = " ".join(str(nome).strip().rstrip(".").split()).upper()
    if chave in _MAPA_CATEGORIAS:
        return _MAPA_CATEGORIAS[chave]
    return chave[:20] + "…" if len(chave) > 21 else chave


def _rotulo_fornecedor(nome: object) -> str:
    limpo = " ".join(str(nome).strip().rstrip(".").split()).upper()
    for sufixo in (" - ME", " - EPP", " LTDA", " EPP", " S/A", " S.A."):
        if limpo.endswith(sufixo) and len(limpo) > len(sufixo) + 4:
            limpo = limpo[: -len(sufixo)].strip().rstrip("-").strip()
    return limpo[:19] + "…" if len(limpo) > 20 else limpo


def _formatar_br(valor: float, casas: int = 2) -> str:
    num = float(valor)
    if casas <= 0:
        inteiro = round(num)
        return f"{inteiro:,}".replace(",", ".")
    texto = f"{num:,.{casas}f}"
    return texto.replace(",", "_").replace(".", ",").replace("_", ".")


def reais(valor: float, casas: int = 2) -> str:
    """Formata número como moeda em reais: R$ 1.003.862,14."""
    return f"R$ {_formatar_br(valor, casas)}"


def pct(valor: float, casas: int = 1) -> str:
    """Formata número como percentual: 93,2%."""
    return f"{_formatar_br(valor, casas)}%"


def numero(valor: float, casas: int = 0) -> str:
    """Formata número com separador de milhar brasileiro: 96.470."""
    return _formatar_br(valor, casas)


def ler(marts: Iterable[str] = MARTS_PAINEL) -> dict[str, pd.DataFrame]:
    """Lê os marts solicitados do banco em somente leitura e fecha a conexão."""
    if not CAMINHO_BANCO.is_file():
        raise FileNotFoundError(
            f"Banco de dados não encontrado em {CAMINHO_BANCO}. "
            "Execute 'uv run python -m pipeline.marts'."
        )

    lista_marts = list(marts)
    for nome in lista_marts:
        if not _IDENTIFICADOR_VALIDO.match(nome):
            raise ValueError(f"Nome de mart inválido: {nome!r}")

    con = duckdb.connect(str(CAMINHO_BANCO), read_only=True)
    try:
        existentes = {
            row[0]
            for row in con.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'marts'"
            ).fetchall()
        }
        faltantes = [m for m in lista_marts if m not in existentes]
        if faltantes:
            raise LookupError(
                "Marts ausentes no banco: "
                + ", ".join(f"marts.{m}" for m in faltantes)
                + ". Execute 'uv run python -m pipeline.marts'."
            )

        resultado: dict[str, pd.DataFrame] = {}
        for nome in lista_marts:
            resultado[nome] = con.execute(f"SELECT * FROM marts.{nome}").df()
        return resultado
    finally:
        con.close()


def _aplicar_layout_base(
    fig: go.Figure,
    titulo: str,
    eixo_x: str,
    eixo_y: str,
    margem_esquerda: int = 72,
    barra_horizontal: bool = False,
) -> go.Figure:
    fig.update_layout(
        template="plotly_white",
        title={
            "text": f"<b>{titulo}</b>",
            "font": {"family": FONTE_PADRAO, "size": 13, "color": COR_TEXTO},
            "x": 0.02,
            "xanchor": "left",
        },
        plot_bgcolor="#FFFFFF",
        paper_bgcolor="#FFFFFF",
        font={"family": FONTE_PADRAO, "size": 11, "color": COR_TEXTO},
        hoverlabel={
            "bgcolor": COR_TEXTO,
            "font_size": 12,
            "font_family": FONTE_PADRAO,
            "font_color": "#FFFFFF",
        },
        margin={"l": margem_esquerda, "r": 24, "t": 48, "b": 58},
        height=370,
    )
    fig.update_xaxes(
        title={
            "text": eixo_x,
            "font": {"family": FONTE_PADRAO, "size": 11, "color": COR_EIXO},
            "standoff": 10,
        },
        showgrid=True,
        gridcolor=COR_GRADE,
        zeroline=False,
        tickfont={"family": FONTE_PADRAO, "size": 11, "color": COR_TEXTO},
        automargin=True,
    )
    fig.update_yaxes(
        title={
            "text": eixo_y,
            "font": {"family": FONTE_PADRAO, "size": 11, "color": COR_EIXO},
            "standoff": 12,
        },
        showgrid=False,
        zeroline=False,
        tickfont={"family": FONTE_PADRAO, "size": 11, "color": COR_TEXTO},
        ticksuffix="  " if barra_horizontal else "",
        automargin=True,
    )
    return fig


def grafico_gastos_mensais(df: pd.DataFrame) -> go.Figure:
    """01 · Linha de desembolso mensal da Cota Parlamentar."""
    dados = df.sort_values("mes").copy()
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=dados["mes"],
            y=dados["despesa_liquida"],
            mode="lines+markers",
            line={"color": COR_PRINCIPAL, "width": 3},
            marker={"size": 8, "color": COR_PRINCIPAL},
            name="Despesa líquida (R$)",
        )
    )
    return _aplicar_layout_base(
        fig,
        "01 · Evolução mensal da Cota Parlamentar (R$)",
        "Mês de competência",
        "Despesa líquida (R$)",
        margem_esquerda=80,
    )


def grafico_categorias(df: pd.DataFrame) -> go.Figure:
    """02 · Top 10 categorias por despesa líquida (barras horizontais, maior em cima)."""
    top = df.sort_values("despesa_liquida", ascending=False).head(10).iloc[::-1]
    rotulos = [_rotulo_categoria(c) for c in top["categoria_despesa"]]
    fig = go.Figure(
        go.Bar(
            x=top["despesa_liquida"],
            y=rotulos,
            customdata=top["categoria_despesa"],
            hovertemplate="<b>%{customdata}</b><br>Despesa: R$ %{x:,.2f}<extra></extra>",
            orientation="h",
            marker_color=COR_PRINCIPAL,
        )
    )
    return _aplicar_layout_base(
        fig,
        "02 · Despesa por categoria (Top 10 · R$)",
        "Despesa líquida (R$)",
        "",
        margem_esquerda=165,
        barra_horizontal=True,
    )


def grafico_partidos(df: pd.DataFrame) -> go.Figure:
    """10 · Top 10 partidos por despesa líquida (barras horizontais, maior em cima)."""
    top = df.sort_values("despesa_liquida", ascending=False).head(10).iloc[::-1]
    fig = go.Figure(
        go.Bar(
            x=top["despesa_liquida"],
            y=top["partido"],
            hovertemplate="<b>Partido %{y}</b><br>Despesa: R$ %{x:,.2f}<extra></extra>",
            orientation="h",
            marker_color=COR_PRINCIPAL,
        )
    )
    return _aplicar_layout_base(
        fig,
        "10 · Despesa por partido (Top 10 · R$)",
        "Despesa líquida (R$)",
        "",
        margem_esquerda=105,
        barra_horizontal=True,
    )


def grafico_gasto_uf(df: pd.DataFrame) -> go.Figure:
    """06 · Top 10 UFs por gasto anual médio por deputado (barras horizontais)."""
    top = df.sort_values("gasto_medio_deputado", ascending=False).head(10).iloc[::-1]
    fig = go.Figure(
        go.Bar(
            x=top["gasto_medio_deputado"],
            y=top["uf"],
            hovertemplate="<b>UF %{y}</b><br>Gasto médio/dep.: R$ %{x:,.2f}<extra></extra>",
            orientation="h",
            marker_color=COR_PRINCIPAL,
        )
    )
    return _aplicar_layout_base(
        fig,
        "06 · Gasto médio/deputado por UF (Top 10)",
        "Gasto médio por deputado (R$)",
        "",
        margem_esquerda=50,
        barra_horizontal=True,
    )


def grafico_fornecedores_ceis(df: pd.DataFrame) -> go.Figure:
    """07 · Top 10 fornecedores listados no CEIS que receberam recursos da CEAP."""
    top = df.sort_values("valor_recebido_total", ascending=False).head(10).iloc[::-1]
    rotulos = [_rotulo_fornecedor(n) for n in top["nome_fornecedor"]]
    cores = [
        COR_DESTAQUE if float(v) > 0 else COR_PRINCIPAL
        for v in top["valor_recebido_em_vigencia"]
    ]
    fig = go.Figure(
        go.Bar(
            x=top["valor_recebido_total"],
            y=rotulos,
            customdata=top["nome_fornecedor"],
            hovertemplate="<b>%{customdata}</b><br>Total recebido: R$ %{x:,.2f}<extra></extra>",
            orientation="h",
            marker_color=cores,
        )
    )
    return _aplicar_layout_base(
        fig,
        "07 · Fornecedores CEIS (âmbar = ativa)",
        "Valor recebido na CEAP (R$)",
        "",
        margem_esquerda=165,
        barra_horizontal=True,
    )


def grafico_glosas(df: pd.DataFrame) -> go.Figure:
    """08 · Top 10 categorias com maior volume de glosa administrativa."""
    top = df.sort_values("valor_glosado", ascending=False).head(10).iloc[::-1]
    rotulos = [_rotulo_categoria(c) for c in top["categoria_despesa"]]
    fig = go.Figure(
        go.Bar(
            x=top["valor_glosado"],
            y=rotulos,
            customdata=top["categoria_despesa"],
            hovertemplate="<b>%{customdata}</b><br>Valor glosado: R$ %{x:,.2f}<extra></extra>",
            orientation="h",
            marker_color=COR_PRINCIPAL,
        )
    )
    return _aplicar_layout_base(
        fig,
        "08 · Glosas por categoria (Top 10 · R$)",
        "Valor glosado / cortado (R$)",
        "",
        margem_esquerda=165,
        barra_horizontal=True,
    )


def grafico_pareto_fornecedores(df: pd.DataFrame) -> go.Figure:
    """09 · Curva de concentração de Pareto dos fornecedores (amostragem se > 500 linhas)."""
    dados = df.sort_values("posicao")
    if len(dados) > 500:
        passo = max(1, len(dados) // 400)
        amostra = dados.iloc[::passo].copy()
        if amostra.iloc[-1]["posicao"] != dados.iloc[-1]["posicao"]:
            amostra = pd.concat([amostra, dados.iloc[[-1]]], ignore_index=True)
        dados = amostra

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=dados["posicao"],
            y=dados["pct_acumulado"],
            mode="lines",
            line={"color": COR_PRINCIPAL, "width": 3},
            name="% acumulado da despesa",
        )
    )
    fig.add_hline(
        y=80,
        line_dash="dash",
        line_color=COR_DESTAQUE,
        annotation_text="<b>80% da despesa (pos. 1.765)</b>",
        annotation_position="bottom right",
        annotation_font={"family": FONTE_PADRAO, "size": 11, "color": COR_TEXTO},
    )
    return _aplicar_layout_base(
        fig,
        "09 · Concentração de Pareto (% acumulado)",
        "Posição do fornecedor no ranking",
        "% acumulado da despesa",
        margem_esquerda=72,
    )
