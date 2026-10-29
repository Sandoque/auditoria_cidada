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

5. CARTÕES E SUBTÍTULOS:
   cartoes(kpi) define os sete cartões executivos uma única vez e html_cartoes()
   os desenha para app.py e relatorio.py. Cada gráfico traz um subtítulo-resposta
   montado só selecionando linhas do mart (maior, menor, primeira que cruza 80%).
"""

import html
import re
import unicodedata
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import NamedTuple

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
COR_NEUTRA = "#64748B"
COR_GRADE = "#CBD5E1"
COR_TEXTO = "#0B1315"
COR_EIXO = "#1E293B"
FONTE_PADRAO = "Segoe UI, Arial, sans-serif"

_MESES_ABREV = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")

# Alcance da sanção vigente (marts.fornecedores_sancionados) -> legenda e marcador do gráfico 07.
_ALCANCES_CEIS: tuple[tuple[str, str, dict], ...] = (
    ("federal", "Vigente · alcance federal", {"color": COR_DESTAQUE}),
    (
        "sem_informacao",
        "Vigente · alcance sem informação",
        {"color": COR_DESTAQUE, "pattern": {"shape": "/", "solidity": 0.5}},
    ),
    ("restrita", "Vigente · restrita a outro órgão", {"color": COR_NEUTRA}),
)
_ROTULO_ALCANCE: dict[str, str] = {
    "federal": "alcance federal",
    "sem_informacao": "alcance sem informação",
    "restrita": "restrita a outro órgão",
}

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


def reais_compacto(valor: float) -> str:
    """Formata moeda trocando só a unidade de exibição: R$ 215,11 mi, R$ 192,1 mil, R$ 840,00."""
    num = float(valor)
    if abs(num) >= 1_000_000:
        return f"R$ {_formatar_br(num / 1_000_000, 2)} mi"
    if abs(num) >= 1_000:
        return f"R$ {_formatar_br(num / 1_000, 1)} mil"
    return reais(num)


def _plural(qtd: float, singular: str, plural: str) -> str:
    return f"{numero(qtd)} {singular if round(float(qtd)) == 1 else plural}"


def _mes_abrev(mes: object) -> str:
    data = pd.Timestamp(mes)
    return f"{_MESES_ABREV[data.month - 1]}/{data.year}"


class Cartao(NamedTuple):
    rotulo: str
    valor: str
    detalhe: str
    alerta: bool = False


def cartoes(kpi: pd.Series) -> list[Cartao]:
    """Os sete cartões executivos, lidos de uma linha de marts.kpis."""
    return [
        Cartao(
            "Despesa líquida · válida",
            reais_compacto(kpi["despesa_total_reais"]),
            reais(kpi["despesa_total_reais"]),
        ),
        Cartao(
            "Ticket médio · por nota",
            reais(kpi["ticket_medio_nota"]),
            f"Mediana: {reais(kpi['ticket_mediana_nota'])}",
        ),
        Cartao(
            "Taxa de glosa · % cortado",
            pct(kpi["pct_glosado"], casas=2),
            f"{reais(kpi['valor_glosado_total'])} cortados",
        ),
        Cartao(
            "Uso da cota · % do teto",
            pct(kpi["pct_teto_utilizado_geral"]),
            f"{numero(kpi['deputados_acima_90_teto'])} de"
            f" {_plural(kpi['deputados_com_teto'], 'deputado', 'deputados')} usaram 90% ou mais",
        ),
        Cartao(
            "Fora do CEIS · % do valor",
            pct(kpi["pct_valor_regular"], casas=2),
            f"{reais_compacto(kpi['despesa_fornecedores_ceis'])} a fornecedores no CEIS",
        ),
        Cartao(
            "Pago em sanção vigente · CEIS",
            reais(kpi["despesa_sancao_vigente"]),
            f"Restrita: {reais_compacto(kpi['despesa_sancao_vigente_restrita'])}"
            f" · sem info: {reais_compacto(kpi['despesa_sancao_vigente_sem_info'])}",
        ),
        Cartao(
            "Sanção vigente · alcance federal",
            reais(kpi["despesa_sancao_vigente_federal"]),
            f"{_plural(kpi['lancamentos_sancao_vigente_federal'], 'nota', 'notas')}"
            f" · {_plural(kpi['fornecedores_sancao_vigente_federal'], 'fornecedor', 'fornecedores')}",
            alerta=True,
        ),
    ]


CSS_CARTOES = f"""
.cards {{
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}}
.card {{
  background: #FFFFFF;
  border: 1px solid {COR_GRADE};
  border-top: 4px solid {COR_PRINCIPAL};
  border-radius: 8px;
  padding: 12px 14px;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.06);
}}
.card-alert {{ border-top-color: {COR_DESTAQUE}; }}
.card-label {{
  font-size: 12.5px;
  font-weight: 600;
  color: {COR_EIXO};
  margin-bottom: 6px;
  line-height: 1.25;
  min-height: 2.5em;
}}
.card-value {{
  font-size: 19px;
  font-weight: 700;
  color: {COR_TEXTO};
}}
.card-alert .card-value {{ color: {COR_DESTAQUE}; }}
.card-detail {{
  margin-top: 6px;
  font-size: 11.5px;
  line-height: 1.3;
  color: {COR_EIXO};
}}
@media (max-width: 1100px) {{
  .cards {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
}}
"""


def html_cartoes(lista: Iterable[Cartao]) -> str:
    """Desenha os cartões em HTML com as classes de CSS_CARTOES."""
    blocos = "\n".join(
        f'<div class="card{" card-alert" if c.alerta else ""}">'
        f'<div class="card-label">{html.escape(c.rotulo)}</div>'
        f'<div class="card-value">{html.escape(c.valor)}</div>'
        f'<div class="card-detail">{html.escape(c.detalhe)}</div>'
        f"</div>"
        for c in lista
    )
    return f'<section class="cards">\n{blocos}\n</section>'


NOTA_TETO = (
    "% do teto = gasto ÷ teto do período. Cada dia de efetivo exercício do mandato (histórico"
    " oficial da Câmara) vale o limite mensal da UF vigente naquele dia dividido pelos dias do mês,"
    " como manda o art. 11 do Ato da Mesa nº 43/2009; os limites são os dos Atos nº 270/2023 e"
    " nº 244/2026. Pode passar de 100%: líderes, vice-líderes e presidentes de comissão têm"
    " adicional de cota, e até quatro trechos aéreos por mês são reembolsados além dela."
    " Concentração alta em um fornecedor é um ponto de atenção, não indício de irregularidade."
)

AVISO_ANO_PARCIAL = (
    "Ano em andamento: a nota pode ser apresentada até 90 dias depois da despesa (art. 4º, § 12,"
    " do Ato da Mesa nº 43/2009), então os meses mais recentes ainda vão crescer e o uso do teto"
    " tende a subir."
)


class Periodo(NamedTuple):
    ano: int
    primeiro_mes: pd.Timestamp
    ultimo_mes: pd.Timestamp
    parcial: bool


def anos(dados: dict[str, pd.DataFrame]) -> list[int]:
    """Anos com dados em marts.kpis, do mais recente para o mais antigo."""
    return sorted((int(a) for a in dados["kpis"]["ano"].unique()), reverse=True)


def do_ano(dados: dict[str, pd.DataFrame], ano: int) -> dict[str, pd.DataFrame]:
    """Recorta cada mart para um ano (só filtro de linhas pela coluna `ano`)."""
    return {nome: df[df["ano"] == ano].reset_index(drop=True) for nome, df in dados.items()}


def periodo(dados_ano: dict[str, pd.DataFrame], hoje: date | None = None) -> Periodo:
    """Primeiro e último mês com dados do ano e se ele ainda está parcial (prazo de 90 dias)."""
    meses = dados_ano["gastos_mensais"]["mes"].sort_values()
    primeiro, ultimo = pd.Timestamp(meses.iloc[0]), pd.Timestamp(meses.iloc[-1])
    hoje = hoje or date.today()
    parcial = ultimo.month < 12 or (hoje - date(ultimo.year, 12, 31)).days < 90
    return Periodo(ultimo.year, primeiro, ultimo, parcial)


def texto_periodo(p: Periodo) -> str:
    sufixo = " (parcial)" if p.parcial else ""
    return f"Ano de {p.ano} · dados de {_mes_abrev(p.primeiro_mes)} a {_mes_abrev(p.ultimo_mes)}{sufixo}"


COLUNAS_TABELA_DEPUTADOS: dict[str, str] = {
    "nome_parlamentar": "Deputado",
    "partido": "Partido",
    "uf": "UF",
    "meses_exercicio": "Meses",
    "despesa_liquida": "Gasto (R$)",
    "pct_teto_utilizado": "% do teto",
    "fornecedores_distintos": "Fornecedores",
    "maior_fornecedor": "Maior fornecedor",
    "pct_maior_fornecedor": "% no maior fornecedor",
    "posicao_maior_gasto": "Posição no gasto",
}


def sem_acento(texto: object) -> str:
    """Minúsculas sem acentos, para busca por nome tolerante a 'joao' x 'João'."""
    decomposto = unicodedata.normalize("NFD", str(texto))
    return "".join(c for c in decomposto if not unicodedata.combining(c)).lower()


def tabela_deputados(
    df: pd.DataFrame,
    uf: str | None = None,
    partido: str | None = None,
    nome: str = "",
) -> pd.DataFrame:
    """Faixa 2 · marts.ranking_deputados filtrado, do maior uso do teto ao menor, com rótulos de exibição."""
    dados = df
    if uf:
        dados = dados[dados["uf"] == uf]
    if partido:
        dados = dados[dados["partido"] == partido]
    termo = sem_acento(nome.strip())
    if termo:
        mascara = pd.Series(
            [termo in sem_acento(n) for n in dados["nome_parlamentar"]], index=dados.index, dtype=bool
        )
        dados = dados.loc[mascara]
    return (
        dados.sort_values(["pct_teto_utilizado", "nome_parlamentar"], ascending=[False, True])
        .loc[:, list(COLUNAS_TABELA_DEPUTADOS)]
        .rename(columns=COLUNAS_TABELA_DEPUTADOS)
        .reset_index(drop=True)
    )


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
    subtitulo: str = "",
) -> go.Figure:
    fig.update_layout(
        template="plotly_white",
        title={
            "text": f"<b>{titulo}</b>",
            "font": {"family": FONTE_PADRAO, "size": 13, "color": COR_TEXTO},
            "subtitle": {
                "text": subtitulo,
                "font": {"family": FONTE_PADRAO, "size": 11, "color": COR_PRINCIPAL},
            },
            "x": 0.02,
            "xanchor": "left",
        },
        separators=",.",
        plot_bgcolor="#FFFFFF",
        paper_bgcolor="#FFFFFF",
        font={"family": FONTE_PADRAO, "size": 11, "color": COR_TEXTO},
        hoverlabel={
            "bgcolor": COR_TEXTO,
            "font_size": 12,
            "font_family": FONTE_PADRAO,
            "font_color": "#FFFFFF",
        },
        margin={"l": margem_esquerda, "r": 24, "t": 72 if subtitulo else 48, "b": 58},
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


def grafico_gastos_mensais(df: pd.DataFrame, parcial: bool = False) -> go.Figure:
    """01 · Linha de desembolso mensal da Cota Parlamentar (num ano parcial, sem apontar 'piso')."""
    dados = df.sort_values("mes").copy()
    subtitulo = ""
    if not dados.empty:
        pico = dados.loc[dados["despesa_liquida"].idxmax()]
        piso = dados.loc[dados["despesa_liquida"].idxmin()]
        subtitulo = f"Pico em {_mes_abrev(pico['mes'])} ({reais_compacto(pico['despesa_liquida'])})"
        subtitulo += (
            " · meses recentes ainda recebem notas"
            if parcial
            else f" · piso em {_mes_abrev(piso['mes'])} ({reais_compacto(piso['despesa_liquida'])})"
        )
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
    fig = _aplicar_layout_base(
        fig,
        "01 · Evolução mensal da Cota Parlamentar (R$)",
        "Mês de competência",
        "Despesa líquida (R$)",
        margem_esquerda=80,
        subtitulo=subtitulo,
    )
    fig.update_xaxes(tickvals=list(dados["mes"]), ticktext=[_mes_abrev(m) for m in dados["mes"]])
    fig.update_yaxes(rangemode="tozero")
    fig.update_layout(height=290)
    return fig


def grafico_categorias(df: pd.DataFrame) -> go.Figure:
    """02 · Top 10 categorias por despesa líquida (barras horizontais, maior em cima)."""
    top = df.sort_values("despesa_liquida", ascending=False).head(10).iloc[::-1]
    rotulos = [_rotulo_categoria(c) for c in top["categoria_despesa"]]
    subtitulo = ""
    if not top.empty:
        lider = top.iloc[-1]
        subtitulo = (
            f"{_rotulo_categoria(lider['categoria_despesa'])} lidera:"
            f" {reais_compacto(lider['despesa_liquida'])} ({pct(lider['pct_total'])} do total)"
        )
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
        subtitulo=subtitulo,
    )


def _marcar_teto(fig: go.Figure, maior_pct: float) -> go.Figure:
    """Eixo X em % com linha tracejada no teto (100%) sempre visível."""
    fig.add_vline(x=100, line_dash="dash", line_color=COR_DESTAQUE, line_width=2)
    fig.update_xaxes(range=[0, max(105.0, float(maior_pct) + 5)], ticksuffix="%")
    return fig


def _subtitulo_mais_menos(ordenado: pd.DataFrame, coluna_nome: str) -> str:
    """'X usa mais: 95,0% do teto · Y usa menos: 63,5%' a partir de um mart já ordenado."""
    if ordenado.empty:
        return ""
    maior, menor = ordenado.iloc[0], ordenado.iloc[-1]
    return (
        f"{maior[coluna_nome]} usa mais: {pct(maior['pct_teto_utilizado'])} do teto"
        f" · {menor[coluna_nome]} usa menos: {pct(menor['pct_teto_utilizado'])}"
    )


def grafico_partidos(df: pd.DataFrame) -> go.Figure:
    """10 · Uso do teto da cota nas 10 maiores bancadas (barras horizontais, maior em cima)."""
    bancadas = (
        df[df["pct_teto_utilizado"].notna()]
        .sort_values(["deputados_ativos", "partido"], ascending=[False, True])
        .head(10)
    )
    ordenado = bancadas.sort_values(["pct_teto_utilizado", "partido"], ascending=[False, True])
    top = ordenado.iloc[::-1]
    fig = go.Figure(
        go.Bar(
            x=top["pct_teto_utilizado"],
            y=top["partido"],
            customdata=top[["deputados_ativos", "despesa_liquida"]],
            hovertemplate=(
                "<b>%{y}</b><br>Uso do teto: %{x:.1f}%<br>Deputados: %{customdata[0]}"
                "<br>Despesa: R$ %{customdata[1]:,.2f}<extra></extra>"
            ),
            orientation="h",
            marker_color=COR_PRINCIPAL,
        )
    )
    fig = _aplicar_layout_base(
        fig,
        "10 · Uso da cota por partido (% do teto)",
        "% do teto · 10 maiores bancadas (tracejado = 100%)",
        "",
        margem_esquerda=105,
        barra_horizontal=True,
        subtitulo=_subtitulo_mais_menos(ordenado, "partido"),
    )
    return _marcar_teto(fig, ordenado["pct_teto_utilizado"].iloc[0] if not ordenado.empty else 0)


def grafico_gasto_uf(df: pd.DataFrame) -> go.Figure:
    """06 · Top 10 UFs pelo uso do teto da cota (gasto ÷ limite mensal × meses de exercício)."""
    ordenado = df.sort_values(["pct_teto_utilizado", "uf"], ascending=[False, True])
    top = ordenado.head(10).iloc[::-1]
    fig = go.Figure(
        go.Bar(
            x=top["pct_teto_utilizado"],
            y=top["uf"],
            customdata=top[["nome_estado", "limite_mensal_cota", "deputados", "deputado_meses"]],
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>Uso do teto: %{x:.1f}%"
                "<br>Teto mensal: R$ %{customdata[1]:,.2f}"
                "<br>Deputados: %{customdata[2]} (%{customdata[3]:,.0f} deputado-meses)<extra></extra>"
            ),
            orientation="h",
            marker_color=COR_PRINCIPAL,
        )
    )
    fig = _aplicar_layout_base(
        fig,
        "06 · Uso da cota por UF (% do teto · Top 10)",
        "% do teto da cota (tracejado = 100%)",
        "",
        margem_esquerda=50,
        barra_horizontal=True,
        subtitulo=_subtitulo_mais_menos(ordenado, "uf"),
    )
    return _marcar_teto(fig, ordenado["pct_teto_utilizado"].iloc[0] if not ordenado.empty else 0)


def grafico_fornecedores_ceis(df: pd.DataFrame) -> go.Figure:
    """07 · Top 10 fornecedores do CEIS por valor pago em sanção vigente, coloridos pelo alcance da sanção."""
    em_vigencia = df[df["valor_recebido_em_vigencia"] > 0]
    top = (
        em_vigencia.sort_values(["valor_recebido_em_vigencia", "valor_recebido_total"], ascending=False)
        .head(10)
        .iloc[::-1]
        .copy()
    )
    top["rotulo"] = [_rotulo_fornecedor(n) for n in top["nome_fornecedor"]]

    fig = go.Figure()
    for chave, legenda, marcador in _ALCANCES_CEIS:
        grupo = top[top["alcance_sancao_vigente"] == chave]
        if grupo.empty:
            continue
        fig.add_trace(
            go.Bar(
                x=grupo["valor_recebido_em_vigencia"],
                y=grupo["rotulo"],
                customdata=grupo[["nome_fornecedor", "valor_recebido_total"]],
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>Pago em sanção vigente: R$ %{x:,.2f}"
                    "<br>Total recebido na CEAP: R$ %{customdata[1]:,.2f}<extra></extra>"
                ),
                orientation="h",
                marker=marcador,
                name=legenda,
            )
        )

    if top.empty:
        subtitulo = "Nenhum pagamento caiu em sanção vigente"
    else:
        maior = top.iloc[-1]
        subtitulo = (
            f"Maior: {_rotulo_fornecedor(maior['nome_fornecedor'])}"
            f" · {reais_compacto(maior['valor_recebido_em_vigencia'])}"
            f" · {_ROTULO_ALCANCE[maior['alcance_sancao_vigente']]}"
        )

    fig = _aplicar_layout_base(
        fig,
        "07 · Pago em sanção vigente (Top 10 · R$)",
        "Valor pago em sanção vigente do CEIS (R$)",
        "",
        margem_esquerda=165,
        barra_horizontal=True,
        subtitulo=subtitulo,
    )
    fig.update_yaxes(categoryorder="array", categoryarray=list(top["rotulo"]))
    fig.update_layout(
        barmode="stack",
        showlegend=True,
        legend={
            "x": 0.99,
            "xanchor": "right",
            "y": 0.02,
            "yanchor": "bottom",
            "traceorder": "normal",
            "bgcolor": "rgba(255, 255, 255, 0.9)",
            "bordercolor": COR_GRADE,
            "borderwidth": 1,
            "font": {"family": FONTE_PADRAO, "size": 10, "color": COR_TEXTO},
        },
    )
    return fig


def grafico_glosas(df: pd.DataFrame) -> go.Figure:
    """08 · Top 10 categorias pela taxa de glosa (% do valor bruto cortado pela Câmara)."""
    top = df.sort_values("pct_valor_glosado", ascending=False).head(10).iloc[::-1]
    rotulos = [_rotulo_categoria(c) for c in top["categoria_despesa"]]
    fig = go.Figure(
        go.Bar(
            x=top["pct_valor_glosado"],
            y=rotulos,
            customdata=top[["categoria_despesa", "valor_glosado", "valor_bruto"]],
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>Taxa de glosa: %{x:.2f}%"
                "<br>Glosado: R$ %{customdata[1]:,.2f} de R$ %{customdata[2]:,.2f}<extra></extra>"
            ),
            orientation="h",
            marker_color=COR_PRINCIPAL,
        )
    )
    subtitulo = ""
    if not top.empty:
        maior_taxa = top.iloc[-1]
        maior_valor = df.sort_values("valor_glosado", ascending=False).iloc[0]
        subtitulo = (
            f"Maior taxa: {_rotulo_categoria(maior_taxa['categoria_despesa'])}"
            f" ({pct(maior_taxa['pct_valor_glosado'])})"
            f" · maior valor: {_rotulo_categoria(maior_valor['categoria_despesa'])}"
        )
    fig = _aplicar_layout_base(
        fig,
        "08 · Taxa de glosa por categoria (Top 10)",
        "Taxa de glosa (% do valor bruto)",
        "",
        margem_esquerda=165,
        barra_horizontal=True,
        subtitulo=subtitulo,
    )
    fig.update_xaxes(ticksuffix="%")
    return fig


def grafico_pareto_fornecedores(df: pd.DataFrame) -> go.Figure:
    """09 · Curva de concentração de Pareto dos fornecedores (amostragem se > 500 linhas)."""
    dados = df.sort_values("posicao")
    cruzamento_80 = dados[dados["pct_acumulado"] >= 80]
    ultima_posicao = dados.iloc[-1]["posicao"] if not dados.empty else 0
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
    subtitulo = ""
    if not cruzamento_80.empty:
        posicao_80 = cruzamento_80.iloc[0]["posicao"]
        fig.add_hline(
            y=80,
            line_dash="dash",
            line_color=COR_DESTAQUE,
            annotation_text=f"<b>80% da despesa (pos. {numero(posicao_80)})</b>",
            annotation_position="bottom right",
            annotation_font={"family": FONTE_PADRAO, "size": 11, "color": COR_TEXTO},
        )
        subtitulo = (
            f"80% da despesa está em {numero(posicao_80)}"
            f" de {_plural(ultima_posicao, 'fornecedor', 'fornecedores')}"
        )
    return _aplicar_layout_base(
        fig,
        "09 · Concentração de Pareto (% acumulado)",
        "Posição do fornecedor no ranking",
        "% acumulado da despesa",
        margem_esquerda=72,
        subtitulo=subtitulo,
    )
