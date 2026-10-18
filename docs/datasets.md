# Dados do primeiro protótipo

A instalação ampliada está em [RPC: 200 produtos em 17 grupos](rpc-dataset.md), com
4.000 recortes separados em train/val/test e uma galeria combinada com as frutas iniciais.
As instruções abaixo preservam a demonstração original com três classes.

O protótipo recebe uma imagem com um produto e retorna uma sugestão de SKU do catálogo
cadastrado. O dataset permite verificar o fluxo e medir reconhecimento em imagens
separadas do treino. Uma foto contendo vários produtos exigirá detecção ou segmentação
antes da classificação; isso fica para outra etapa.

## Escolha do dataset

| Dataset | Uso adequado | Acesso e licença informados pelos autores | Decisão |
| --- | --- | --- | --- |
| [Grocery Store Dataset](https://github.com/marcusklasson/GroceryStoreDataset) | Classificação, 81 classes finas e 42 amplas, frutas, vegetais e embalagens | Imagens e splits no GitHub; [LICENSE MIT do repositório](https://github.com/marcusklasson/GroceryStoreDataset/blob/master/LICENSE) | Escolhido para a demonstração pequena |
| [RPC](https://rpc-dataset.github.io/) | Produtos individuais no treino e múltiplos produtos no checkout | 15 GB; [Kaggle indicado pelos autores](https://www.kaggle.com/datasets/diyer22/retail-product-checkout-dataset); CC BY-NC-SA 4.0 | Subset de 200 SKUs instalado; val/test adaptados com recortes anotados para classificação |
| [SKU110K](https://github.com/eg4000/SKU110K_CVPR19) | Detectar e contar itens em prateleiras densas | Download S3/Drive no README; uso acadêmico e não comercial | Não fornece o catálogo de identidade de produtos necessário para o caixa |

O Grocery Store Dataset contém produtos coletados em mercados estrangeiros. Esses
rótulos não representam um catálogo de supermercado brasileiro. Antes de uma implantação,
será necessário obter fotos dos SKUs reais sob a câmera, iluminação e posição do caixa.
O arquivo LICENSE original é preservado junto ao subset; fotos icônicas e descrições
comerciais não são baixadas.

## Aquisição reproduzível

```powershell
uv run caixa dataset-download --output data/grocery --classes 6 16 63 --train-per-class 10 --eval-per-class 5
```

São selecionadas Banana (6), Orange (16) e Cucumber (63), até 10 imagens de treino e
5 de cada split de avaliação por classe: no máximo 60 imagens. A ordem vem dos manifestos
oficiais. Para essa seleção há imagens nos três splits. Classes diferentes podem não
existir na validação; o comando informa o problema sem fabricar outro split.

A origem fica fixada no commit
`fc80ba90f803d79d0383df52c5a4ac5de99ff6fc`, consultado no repositório oficial com
`git ls-remote`. O download usa somente `raw.githubusercontent.com` e esse commit.
Não clona o repositório inteiro e não depende de login no Kaggle.

```text
data/grocery/
  LICENSE
  catalog.csv
  source_manifest.json
  metadata/{classes.csv,train.txt,val.txt,test.txt}
  train/{6,16,63}/*.jpg
  val/{6,16,63}/*.jpg
  test/{6,16,63}/*.jpg
```

Cada linha oficial de split contém `caminho, classe_fina, classe_ampla`.
[classes.csv oficial](https://github.com/marcusklasson/GroceryStoreDataset/blob/master/dataset/classes.csv)
mapeia IDs para nomes. O nome da pasta é o SKU demonstrativo usado no catálogo.

`source_manifest.json` registra revisão, URLs, limites efetivos por split, caminhos locais,
SHA256 de metadados e imagens e `prices_are_demo: true`. `catalog.csv` tem as colunas
`sku,name,price`. **Todos os preços são fictícios: R$ 1,00 por unidade para testar o
fluxo; não são preços do dataset, nem uma regra de venda de hortifruti por peso.**

O destino deve estar vazio ou não existir. O downloader valida caminhos e rótulos,
recusa imagens idênticas entre splits e só publica o diretório após terminar o download.
Falhas não deixam um dataset parcialmente preparado. Não há imagens de treino no Git.

## Treino, validação, teste e uso offline

1. Gere o índice DINOv2 somente com `data/grocery/train`.
2. Ajuste similaridade mínima e margem usando `data/grocery/val`.
3. Meça uma vez em `data/grocery/test` após escolher os limiares. Registre tamanho do
   subset, acurácia, cobertura e erros; uma demonstração com três classes não valida
   operação comercial nem estima desempenho em novos SKUs.
4. Depois de baixar as imagens e os pesos DINOv2, preserve `data/grocery`, o cache de
   pesos e o índice em `artifacts`. A inferência pode ocorrer sem rede.

Usar os vetores DINOv2 de imagens conhecidas é a etapa de cadastro/treino deste protótipo;
não treinamos uma rede neural do zero. Produtos desconhecidos, embalagens muito parecidas,
oclusão e mudança de domínio precisam de avaliação e podem exigir revisão humana.
