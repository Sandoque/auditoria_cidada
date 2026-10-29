"""Gerador do relatório executivo estático em HTML (`relatorio.html`).

SPEC DO MÓDULO (Fonte da Verdade):
1. Lê os marts com painel.ler(), formata os cartões com painel.reais/pct/numero e
   monta os sete gráficos com as funções de painel.py. Não importa streamlit.
2. Escreve relatorio.html na raiz do projeto com as quatro faixas do painel na
   mesma ordem. A biblioteca Plotly vem do CDN uma única vez no primeiro gráfico
   (include_plotlyjs="cdn") e nos demais include_plotlyjs=False, com div_id fixos
   ("g01" a "g07") para determinismo entre execuções.
3. Inclui rodapé com a data e hora de geração ("Dados de DD/MM/AAAA HH:MM") e
   imprime o caminho do arquivo e seu tamanho em KB.
"""

from datetime import datetime
from pathlib import Path
import sys

import painel

CAMINHO_RELATORIO = Path(__file__).resolve().parent / "relatorio.html"


def gerar_relatorio(caminho_saida: Path = CAMINHO_RELATORIO) -> Path:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    dados = painel.ler()
    kpi = dados["kpis"].iloc[0]

    cartoes = [
        ("Despesa líquida · válida", painel.reais(kpi["despesa_total_reais"]), False),
        ("Ticket médio · por nota", painel.reais(kpi["ticket_medio_nota"]), False),
        ("Taxa de glosa · % cortado", painel.pct(kpi["pct_glosado"], casas=2), False),
        ("Fornecedores recorrentes · 2+", painel.pct(kpi["pct_fornecedores_recorrentes"], casas=2), False),
        ("Valor regular · fora do CEIS", painel.pct(kpi["pct_valor_regular"], casas=2), False),
        ("Pago em sanção ativa · CEIS", painel.reais(kpi["despesa_sancao_vigente"]), True),
        ("Notas em sanção ativa · CEIS", painel.numero(kpi["lancamentos_sancao_vigente"], casas=0), True),
    ]

    html_cartoes = "\n".join(
        f'<div class="card {"card-alert" if alerta else ""}">'
        f'<div class="card-label">{rotulo}</div>'
        f'<div class="card-value">{valor}</div>'
        f"</div>"
        for rotulo, valor, alerta in cartoes
    )

    g01 = painel.grafico_gastos_mensais(dados["gastos_mensais"]).to_html(
        full_html=False, include_plotlyjs="cdn", div_id="g01"
    )
    g02 = painel.grafico_categorias(dados["gastos_por_categoria"]).to_html(
        full_html=False, include_plotlyjs=False, div_id="g02"
    )
    g03 = painel.grafico_partidos(dados["gastos_por_partido"]).to_html(
        full_html=False, include_plotlyjs=False, div_id="g03"
    )
    g04 = painel.grafico_gasto_uf(dados["gasto_medio_por_uf"]).to_html(
        full_html=False, include_plotlyjs=False, div_id="g04"
    )
    g05 = painel.grafico_fornecedores_ceis(dados["fornecedores_sancionados"]).to_html(
        full_html=False, include_plotlyjs=False, div_id="g05"
    )
    g06 = painel.grafico_glosas(dados["glosa_por_categoria"]).to_html(
        full_html=False, include_plotlyjs=False, div_id="g06"
    )
    g07 = painel.grafico_pareto_fornecedores(dados["fornecedores_pareto"]).to_html(
        full_html=False, include_plotlyjs=False, div_id="g07"
    )

    carimbo = datetime.now().strftime("%d/%m/%Y %H:%M")

    html = f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Auditoria Cidadã · CEAP 2025 × Sanções CEIS/CGU</title>
  <style>
    :root {{
      --bg: #f4f6f4;
      --surface: #ffffff;
      --ink: #10171a;
      --muted: #4a5a5e;
      --line: #cdd6cf;
      --accent: #1a6b52;
      --amber: #b85c00;
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
    }}
    .sub {{
      margin: 0;
      color: var(--muted);
      font-size: 14px;
    }}
    .cards {{
      display: grid;
      grid-template-columns: repeat(7, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 16px;
    }}
    .card {{
      background: var(--surface);
      border: 1px solid var(--line);
      border-top: 3px solid var(--accent);
      border-radius: 8px;
      padding: 12px 14px;
    }}
    .card-alert {{
      border-top-color: var(--amber);
    }}
    .card-label {{
      font-size: 12px;
      color: var(--muted);
      margin-bottom: 6px;
    }}
    .card-value {{
      font-size: 20px;
      font-weight: 700;
    }}
    .card-alert .card-value {{
      color: var(--amber);
    }}
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
    footer {{
      margin-top: 12px;
      font-size: 13px;
      color: var(--muted);
      text-align: right;
    }}
    @media (max-width: 1100px) {{
      .cards {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .row-3 {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Auditoria Cidadã · Cota Parlamentar (CEAP 2025) × Sanções CEIS/CGU</h1>
    <p class="sub">Visão da operação completa (jan/2025 a dez/2025) · Números lidos diretamente da camada marts</p>
  </header>

  <section class="cards">
    {html_cartoes}
  </section>

  <section class="row-full">
    {g01}
  </section>

  <section class="row-3">
    <div class="chart-box">{g02}</div>
    <div class="chart-box">{g03}</div>
    <div class="chart-box">{g04}</div>
  </section>

  <section class="row-3">
    <div class="chart-box">{g05}</div>
    <div class="chart-box">{g06}</div>
    <div class="chart-box">{g07}</div>
  </section>

  <footer>Dados de {carimbo} · Pipeline Auditoria Cidadã (DuckDB + Python)</footer>
</body>
</html>
"""
    caminho_saida.write_text(html, encoding="utf-8")
    tamanho_kb = caminho_saida.stat().st_size / 1024.0
    print(f"✓ {caminho_saida} ({tamanho_kb:.1f} KB)")
    return caminho_saida


if __name__ == "__main__":
    gerar_relatorio()
