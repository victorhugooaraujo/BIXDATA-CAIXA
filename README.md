# Caixa inteligente — protótipo 0.1

Reconhece **um produto por imagem**, sem código de barras, usando DINOv2 pré-treinado e uma
galeria de exemplos. O MySQL fornece nome e preço. Imagens ambíguas retornam `requires_review`.
Interface inicial por terminal; sem pagamentos ou contagem de vários itens.

Stack: **Python 3.15.0 · uv 0.13.1 · PyTorch 2.14.1 CPU · DINOv2 ViT-S/14 · MySQL 8.4 · Docker**.
Dependências fixadas no `uv.lock`. Veja [arquitetura](docs/architecture.md),
[datasets](docs/datasets.md) e [fluxo Git](CONTRIBUTING.md).

A pasta local entregue já contém a amostra e a galeria prontas, ignoradas pelo Git.
Nesse caso, pule `dataset-download` e `index` nos passos abaixo. Em um clone novo, execute
o fluxo completo. O downloader exige destino vazio e não sobrescreve um dataset existente.

## Executar com Docker

Instale Docker com Compose v2. No PowerShell, dentro desta pasta:

```powershell
Copy-Item .env.example .env
docker compose up -d --wait mysql
docker compose build app
docker compose run --rm app --help
docker compose run --rm app dataset-download
docker compose run --rm app init-db
docker compose run --rm app catalog-import data/grocery/catalog.csv
docker compose run --rm app index
docker compose run --rm app evaluate --images data/grocery/val
docker compose run --rm app evaluate --images data/grocery/test
```

O download padrão seleciona banana, laranja e pepino: até 10 imagens de treino e 5 de cada
split de avaliação por classe. As divisões oficiais são preservadas. A primeira indexação baixa
o código DINOv2 e aproximadamente 84 MB de pesos. Dataset, galeria e cache ficam fora do Git.

Reconhecer uma imagem do teste:

```powershell
$imagem = (Get-ChildItem data/grocery/test/6 -File | Select-Object -First 1).Name
docker compose run --rm app recognize "data/grocery/test/6/$imagem"
```

Para sua própria foto, coloque o arquivo em `data/minha-foto.jpg`:

```powershell
docker compose run --rm app recognize data/minha-foto.jpg
```

O JSON contém candidatos, similaridade de cosseno, margem entre os dois melhores SKUs e,
quando aceito e cadastrado, produto e preço unitário em reais. **Preços do CSV são fictícios**,
por unidade, somente para demonstração. Edite `catalog.csv` e reimporte para mudar preços.
Produtos reconhecidos sem cadastro também pedem revisão.

Use `--min-similarity` e `--min-margin` em `recognize` e `evaluate` para experimentar limiares.
Calibre no `val` e reserve `test` para a avaliação final. Similaridade não é probabilidade.
Uma foto com vários itens pode produzir um palpite incorreto; esta versão não detecta essa situação.

```powershell
docker compose down
```

O banco e o cache permanecem nos volumes Docker. Credenciais do `.env.example` são locais de
desenvolvimento. Para senhas com caracteres especiais, codifique-as na URL `DATABASE_URL`;
no Compose o ambiente de exemplo deve usar senha simples, pois a URL é montada por interpolação.

## Executar Python localmente

Instale [uv](https://docs.astral.sh/uv/getting-started/installation/). O uv instala Python 3.15
quando necessário. Mantenha o MySQL acessível (por exemplo, via Compose).

```powershell
Copy-Item .env.example .env
uv sync --locked
docker compose up -d --wait mysql
uv run --locked caixa dataset-download
uv run --locked caixa init-db
uv run --locked caixa catalog-import data/grocery/catalog.csv
uv run --locked caixa index
uv run --locked caixa evaluate
$imagem = Get-ChildItem data/grocery/test/6 -File | Select-Object -First 1
uv run --locked caixa recognize $imagem.FullName
```

MySQL local usa a `DATABASE_URL` do `.env`; dentro do Compose, o host vira `mysql`.
Para MySQL sem Docker, crie o banco/usuário e ajuste a URL. `init-db` cria somente as tabelas.
O projeto instala PyTorch CPU; não promete execução CUDA sem configuração adicional de wheels.

Com imagens próprias, use `data/meus-produtos/train/<sku>/foto.jpg` e um CSV `sku,name,price`.
Cadastre pelo menos duas classes e gere a galeria:

```powershell
uv run --locked caixa catalog-import data/meus-produtos/catalog.csv
uv run --locked caixa index --images data/meus-produtos/train --gallery artifacts/minha-galeria.npz
uv run --locked caixa recognize data/minha-foto.jpg --gallery artifacts/minha-galeria.npz
```

Não use imagens de validação/teste na pasta de treino. O comando `index` extrai referências;
ele não treina nem ajusta os pesos DINOv2.

## Verificar

```powershell
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked pytest
```

Os testes padrão não baixam imagens/pesos e cobrem splits, galeria, rejeição e catálogo.
O teste MySQL real precisa de `TEST_DATABASE_URL`; a CI configura um MySQL 8.4 dedicado.
Consulte [validação executada](docs/validation.md) para os resultados e limitações locais.

Próximos passos: validar com fotos do caixa, calibrar produtos desconhecidos, integrar câmera
e depois estudar detecção/contagem com o RPC para imagens de múltiplos itens.
