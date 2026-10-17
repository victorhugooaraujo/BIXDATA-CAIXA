# Caixa inteligente — protótipo 0.1

Um produto por imagem: DINOv2 congelado, galeria visual e catálogo de preços MySQL.
Sem pagamentos, câmera contínua ou contagem de múltiplos itens.

Prepare um MySQL com banco e usuário próprios, copie `.env.example` para `.env` e ajuste DATABASE_URL.
Execute `uv sync --locked`, `uv run caixa dataset-download`, `uv run caixa init-db`,
`uv run caixa catalog-import data/grocery/catalog.csv`, `uv run caixa index` e `uv run caixa evaluate`.
Use `uv run caixa recognize caminho/da/foto.jpg` para sugerir o produto e consultar o preço.
Os preços do CSV são fictícios. Casos ambíguos pedem revisão.

Veja docs/architecture.md, docs/datasets.md e CONTRIBUTING.md. Docker/CI vêm no próximo commit.
