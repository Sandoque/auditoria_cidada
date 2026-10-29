"""Gerador do relatório executivo estático em HTML (`relatorio.html`).

SPEC DO MÓDULO (Fonte da Verdade):
1. Lê os marts com painel.ler(), desenha os cartões com painel.cartoes() e
   painel.html_cartoes(), a tabela de deputados com painel.tabela_deputados() e
   os sete gráficos com as funções de painel.py. Não importa streamlit.
2. Escreve uma página por ano com as cinco faixas do painel na mesma ordem:
   relatorio.html para o ano mais recente e relatorio_AAAA.html para cada ano
   anterior, todas com links entre os anos e aviso quando o ano está parcial.
   Em cada página, a biblioteca Plotly vem do CDN uma única vez no primeiro gráfico
   da página (include_plotlyjs="cdn") e nos demais include_plotlyjs=False, com
   div_id fixos ("g01" a "g07", na ordem da página) para determinismo entre execuções.
3. A tabela de deputados vem renderizada no HTML (funciona sem JavaScript) e os
   filtros por UF, partido e nome usam JavaScript puro, sem biblioteca externa.
   A marcação omite tags de fechamento opcionais para caber no limite de tamanho.
4. Inclui rodapé com a data e hora de geração ("Dados de DD/MM/AAAA HH:MM") e
   imprime o caminho do arquivo e seu tamanho em KB.
"""

import html
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

import painel

CAMINHO_RELATORIO = Path(__file__).resolve().parent / "relatorio.html"

_CSS_TABELA = """
    .deputados h2 { margin: 6px 8px 10px; font-size: 16px; }
    .filtros {
      display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end;
      margin: 0 8px 10px; font-size: 13px; font-weight: 600; color: var(--muted);
    }
    .filtros label { display: flex; flex-direction: column; gap: 4px; }
    .filtros select, .filtros input {
      font: inherit; font-weight: 400; min-height: 34px; padding: 6px 8px;
      border: 1px solid var(--line); border-radius: 6px; background: var(--surface); color: var(--ink);
    }
    .filtros .f-nome { flex: 1 1 260px; }
    #f-contagem { margin-left: auto; font-weight: 500; }
    .tabela-rolagem { max-height: 440px; overflow: auto; border-top: 1px solid var(--line); }
    #t-deputados { width: 100%; border-collapse: collapse; font-size: 12.5px; }
    #t-deputados th {
      position: sticky; top: 0; z-index: 1; background: var(--bg);
      padding: 8px; text-align: left; white-space: nowrap; border-bottom: 1px solid var(--line);
    }
    #t-deputados td { padding: 6px 8px; white-space: nowrap; border-bottom: 1px solid #e2e8f0; }
    #t-deputados :is(th, td):is(:nth-child(4), :nth-child(5), :nth-child(6), :nth-child(7), :nth-child(9), :nth-child(10)) {
      text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums;
    }
    #t-deputados td:nth-child(6) { position: relative; z-index: 0; min-width: 110px; }
    #t-deputados td:nth-child(6) i {
      position: absolute; left: 8px; top: 6px; bottom: 6px; max-width: calc(100% - 16px);
      background: rgba(26, 107, 82, 0.18); border-radius: 3px; z-index: -1;
    }
    .nota { margin: 10px 8px 4px; font-size: 12px; line-height: 1.45; color: var(--muted); }
"""

_JS_FILTRO_DEPUTADOS = r"""
(function () {
  var uf = document.getElementById("f-uf");
  var partido = document.getElementById("f-partido");
  var nome = document.getElementById("f-nome");
  var contagem = document.getElementById("f-contagem");
  var normalizar = function (t) {
    return t.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  };
  var linhas = Array.prototype.map.call(document.querySelectorAll("#t-deputados tbody tr"), function (tr) {
    return { tr: tr, nome: normalizar(tr.cells[0].textContent), partido: tr.cells[1].textContent, uf: tr.cells[2].textContent };
  });
  function filtrar() {
    var termo = normalizar(nome.value.trim());
    var visiveis = 0;
    linhas.forEach(function (l) {
      var ok = (!uf.value || l.uf === uf.value)
        && (!partido.value || l.partido === partido.value)
        && (!termo || l.nome.indexOf(termo) !== -1);
      l.tr.hidden = !ok;
      if (ok) { visiveis += 1; }
    });
    contagem.textContent = visiveis + (visiveis === 1 ? " deputado exibido" : " deputados exibidos");
  }
  [uf, partido, nome].forEach(function (el) { el.addEventListener("input", filtrar); });
  filtrar();
})();
"""


def _ou_traco(valor: object, formatar) -> str:
    return "—" if pd.isna(valor) else formatar(valor)


def _html_opcoes(valores: pd.Series) -> str:
    return "".join(f'<option value="{html.escape(v)}">{html.escape(v)}' for v in sorted(valores.dropna().unique()))


def _html_tabela_deputados(tabela: pd.DataFrame) -> str:
    """Linhas da Faixa 2 com marcação enxuta (sem </td> e </tr>, opcionais no HTML5)."""
    cabecalho = "".join(f"<th>{html.escape(c)}" for c in tabela.columns)
    linhas = []
    for r in tabela.to_dict("records"):
        uso = r["% do teto"]
        barra = "" if pd.isna(uso) else f'<i style="width:{min(float(uso), 100.0):.1f}%"></i>'
        linhas.append(
            f"<tr><td>{html.escape(str(r['Deputado']))}"
            f"<td>{html.escape(str(r['Partido']))}"
            f"<td>{html.escape(str(r['UF']))}"
            f"<td>{painel.numero(r['Meses'], 1)}"
            f"<td>{painel.reais(r['Gasto (R$)'])}"
            f"<td>{barra}{_ou_traco(uso, painel.pct)}"
            f"<td>{painel.numero(r['Fornecedores'])}"
            f"<td>{html.escape(str(r['Maior fornecedor']))}"
            f"<td>{_ou_traco(r['% no maior fornecedor'], painel.pct)}"
            f"<td>{painel.numero(r['Posição no gasto'])}º"
        )
    return f"<thead><tr>{cabecalho}</thead>\n<tbody>\n" + "\n".join(linhas) + "\n</tbody>"


def _caminho_do_ano(caminho_saida: Path, ano: int, mais_recente: int) -> Path:
    return caminho_saida if ano == mais_recente else caminho_saida.with_name(f"{caminho_saida.stem}_{ano}.html")


def _html_navegacao(ano_atual: int, anos: list[int], caminho_saida: Path) -> str:
    itens = [
        f'<strong aria-current="page">{a}</strong>'
        if a == ano_atual
        else f'<a href="{_caminho_do_ano(caminho_saida, a, anos[0]).name}">{a}</a>'
        for a in anos
    ]
    return '<nav class="anos">Ano: ' + " · ".join(itens) + "</nav>"


def _html_pagina(dados: dict[str, pd.DataFrame], ano: int, anos: list[int], caminho_saida: Path) -> str:
    periodo = painel.periodo(dados)
    aviso = f'<p class="aviso">{html.escape(painel.AVISO_ANO_PARCIAL)}</p>' if periodo.parcial else ""
    html_cartoes = painel.html_cartoes(painel.cartoes(dados["kpis"].iloc[0]))
    ranking = dados["ranking_deputados"]
    tabela = painel.tabela_deputados(ranking)

    figuras = [
        painel.grafico_gasto_uf(dados["gasto_medio_por_uf"]),
        painel.grafico_partidos(dados["gastos_por_partido"]),
        painel.grafico_categorias(dados["gastos_por_categoria"]),
        painel.grafico_fornecedores_ceis(dados["fornecedores_sancionados"]),
        painel.grafico_glosas(dados["glosa_por_categoria"]),
        painel.grafico_pareto_fornecedores(dados["fornecedores_pareto"]),
        painel.grafico_gastos_mensais(dados["gastos_mensais"], parcial=periodo.parcial),
    ]
    g = [
        fig.to_html(full_html=False, include_plotlyjs="cdn" if i == 0 else False, div_id=f"g{i + 1:02d}")
        for i, fig in enumerate(figuras)
    ]

    carimbo = datetime.now().strftime("%d/%m/%Y %H:%M")
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Auditoria Cidadã · CEAP {ano} × Sanções CEIS/CGU</title>
  <style>
    :root {{
      --bg: #f4f6f4;
      --surface: #ffffff;
      --ink: #0b1315;
      --muted: #1e293b;
      --line: #cbd5e1;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 24px 32px;
      background: var(--bg);
      color: var(--ink);
      font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
    }}
    header {{
      margin-bottom: 18px;
    }}
    h1 {{
      margin: 0 0 4px 0;
      font-size: 24px;
      color: var(--ink);
    }}
    .sub {{
      margin: 0;
      color: var(--muted);
      font-size: 14px;
      font-weight: 500;
    }}
    {painel.CSS_CARTOES}
    .row-full {{
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 8px;
      margin-bottom: 16px;
    }}
    .row-3 {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 16px;
      margin-bottom: 16px;
    }}
    .chart-box {{
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 8px;
    }}
    {_CSS_TABELA}
    .anos {{ margin: 0 0 6px; font-size: 14px; color: var(--muted); }}
    .anos a {{ color: #1a6b52; font-weight: 600; }}
    .aviso {{
      margin: 10px 0 0;
      padding: 8px 12px;
      border-left: 4px solid #b85c00;
      background: var(--surface);
      font-size: 13.5px;
      color: var(--ink);
    }}
    footer {{
      margin-top: 12px;
      font-size: 13px;
      color: var(--muted);
      text-align: right;
    }}
    @media (max-width: 1100px) {{
      .row-3 {{ grid-template-columns: 1fr; }}
    }}
    @media (max-width: 600px) {{
      body {{ padding: 16px; }}
    }}
  </style>
</head>
<body>
  <header>
    {_html_navegacao(ano, anos, caminho_saida)}
    <h1>Auditoria Cidadã · Cota Parlamentar (CEAP {ano}) × Sanções CEIS/CGU</h1>
    <p class="sub">{painel.texto_periodo(periodo)} · Números lidos diretamente da camada marts</p>
    {aviso}
  </header>

  {html_cartoes}

  <section class="row-full deputados">
    <h2>Uso da cota por deputado</h2>
    <div class="filtros">
      <label>UF <select id="f-uf"><option value="">Todas{_html_opcoes(ranking["uf"])}</select></label>
      <label>Partido <select id="f-partido"><option value="">Todos{_html_opcoes(ranking["partido"])}</select></label>
      <label class="f-nome">Nome do deputado <input id="f-nome" type="search" placeholder="Digite parte do nome, com ou sem acento"></label>
      <span id="f-contagem" aria-live="polite">{painel.numero(len(tabela))} deputados exibidos</span>
    </div>
    <div class="tabela-rolagem">
      <table id="t-deputados">
{_html_tabela_deputados(tabela)}
      </table>
    </div>
    <p class="nota">{html.escape(painel.NOTA_TETO)}</p>
  </section>

  <section class="row-3">
    <div class="chart-box">{g[0]}</div>
    <div class="chart-box">{g[1]}</div>
    <div class="chart-box">{g[2]}</div>
  </section>

  <section class="row-3">
    <div class="chart-box">{g[3]}</div>
    <div class="chart-box">{g[4]}</div>
    <div class="chart-box">{g[5]}</div>
  </section>

  <section class="row-full">
    {g[6]}
  </section>

  <footer>Dados de {carimbo} · Pipeline Auditoria Cidadã (DuckDB + Python)</footer>
  <script>{_JS_FILTRO_DEPUTADOS}</script>
</body>
</html>
"""


def gerar_relatorio(caminho_saida: Path = CAMINHO_RELATORIO) -> Path:
    """Grava uma página por ano e devolve o caminho da página do ano mais recente."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    dados_todos = painel.ler()
    anos = painel.anos(dados_todos)
    for ano in anos:
        caminho = _caminho_do_ano(caminho_saida, ano, anos[0])
        caminho.write_text(
            _html_pagina(painel.do_ano(dados_todos, ano), ano, anos, caminho_saida), encoding="utf-8"
        )
        tamanho_kb = caminho.stat().st_size / 1024.0
        print(f"✓ {caminho} ({tamanho_kb:.1f} KB)")
    return caminho_saida


if __name__ == "__main__":
    gerar_relatorio()
