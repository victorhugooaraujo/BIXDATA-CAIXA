# Fluxo de trabalho

Usamos branches curtas a partir de `main`, pull requests e Conventional Commits.
O prefixo `codex/` identifica branches criadas pelo agente; branches humanas podem usar `feat/`,
`fix/` ou `docs/`.

```sh
git switch main
git switch -c feat/camera-capture
uv sync --locked
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked pytest
git add <arquivos relacionados>
git commit -m "feat(capture): add single-frame camera capture"
```

Cada commit resolve uma mudança coerente e deve manter seus testes passando. Exemplos:
`chore(project): configure uv and Python 3.15`, `feat(dataset): prepare grocery subset`,
`fix(vision): reject ambiguous product matches`, `docs: explain local setup`.

O PR descreve comportamento, validação e limitações. Revise e faça merge em `main` após a CI.
Não versionar `.env`, fotos do usuário, datasets, pesos ou galerias geradas.

Para testar MySQL de verdade, use um banco dedicado e defina `TEST_DATABASE_URL` com
`mysql+pymysql://...`. O teste cria sua tabela se necessário, grava um SKU exclusivo e
remove somente esse SKU ao terminar. Sem essa variável, esse teste fica marcado como skipped;
os testes unitários usam SQLite em memória apenas para verificar o código do catálogo.
