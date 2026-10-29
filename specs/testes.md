# Spec da Etapa 5 — Testes Unitários (`test/test_*.py`)

## CONTEXTO
Suíte de testes unitários para o pipeline de Auditoria Cidadã e Compliance, verificando as regras de cada módulo sobre entradas sintéticas controladas.

## REGRAS E PROIBIÇÕES
1. **Meta de Coverage**: >= 60% de cobertura de linhas no total do código Python do pipeline (`pipeline/`, `painel.py` e `relatorio.py`), configurado com `fail_under = 60` no `pyproject.toml`.
2. **Isolamento Total (`tmp_path` + `monkeypatch`)**: Nenhum teste abre `auditoria.duckdb` nem lê os arquivos reais de `raw/`.
3. **Dado Inventado, Resultado da Regra**: Cada linha de entrada sintética possui comentário explicando qual caso de borda ela exercita. Nenhum número medido na base real (`171059`, `215109771`) aparece nos testes.
4. **Sem Atalhos**: Proibido teste sem `assert`, `skip`, `xfail` ou `pytest.approx` para valores monetários.
