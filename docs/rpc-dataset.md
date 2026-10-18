# RPC: produtos de mercado para testes mais variados

O [RPC oficial](https://rpc-dataset.github.io/) tem **200 SKUs em 17 grupos**:
salgadinhos, frutas secas, alimentos secos, bebidas instantâneas, macarrão instantâneo,
sobremesas, bebidas, bebidas alcoólicas, leites, enlatados, chocolates, chicletes,
balas, temperos, higiene pessoal, lenços/papéis e papelaria.

Instalamos uma **amostra balanceada de todos os 200 produtos**, a partir da distribuição
dos autores [no Kaggle](https://www.kaggle.com/datasets/diyer22/retail-product-checkout-dataset),
fixada na versão **5**. As imagens também estão em um
[espelho público no Hugging Face](https://huggingface.co/datasets/benjamintli/retail-product-checkout),
fixado em `c86266a8f08920fea0341994863fe747ac783bc6`.
Não é o download integral de aproximadamente 15,9 GB.

| Divisão | Imagens por produto | Total de recortes |
| --- | ---: | ---: |
| train | 12 | 2.400 |
| val | 4 | 800 |
| test | 4 | 800 |
| Total | 20 | 4.000 |

A seleção é determinística (seed 42). Cada SKU usa imagens-fonte distintas dentro do
seu split; treino/validação/teste seguem as divisões oficiais. Cenas fáceis têm preferência
na amostra de avaliação. No modo Hugging Face, treino utiliza o conjunto oficial
completo, mas a avaliação usa os primeiros arquivos Parquet suficientes para cobrir
as 200 classes. Isso não é uma amostragem uniforme de todo o benchmark. Os arquivos
selecionados ficam no cache para repetir ou ampliar a instalação.

O download Parquet inclui todos os 53.739 exemplares de treino e os pacotes iniciais
de validação/teste, ocupando aproximadamente **10 GB no cache**. SHA256 de cada pacote,
classe, caixas e dimensões das imagens utilizadas são conferidos antes do uso.

## O que estes dados permitem medir

O treino original contém um item por imagem; val/test contêm vários itens. O adaptador
recorta **as caixas verdadeiras anotadas pelos autores** em todas as divisões, com margem
de 5%, limitando o lado maior a 512 pixels. O arquivo `source_manifest.json` preserva
imagem-fonte, caixa, IDs oficiais, split e SHA256 do original e do recorte.

Esse protocolo mede **classificação de objetos já localizados**. Não mede detecção,
contagem, geração de carrinho ou reconhecimento da cena inteira. Os resultados não são
comparáveis ao benchmark oficial de checkout do RPC. Alguns recortes de val/test podem
conter oclusão e pedaços de produtos vizinhos. Os limiares continuam precisando de calibração.

Os SKUs usam o prefixo `rpc-`, evitando colisões com IDs do Grocery Store Dataset.
O catálogo exibe grupo e ID RPC, não inventa marcas em português. Os nomes originais em
chinês estão em `metadata/original_product_names.json`. Os preços de R$ 1,00 são fictícios.
O RPC é de produtos coletados na China: não fornece automaticamente o SKU exato de uma
embalagem brasileira ou de uma marca/sabor que nunca foi cadastrado.

## Reproduzir a instalação

```powershell
uv run --locked caixa dataset-rpc
```

Destino padrão: `data/rpc`. Cache: `.cache/rpc/v5`. O destino deve ser novo;
uma pasta existente nunca é sobrescrita. Interrupções conservam o cache e não publicam
um dataset incompleto. Abra `data/rpc/preview.html` para navegar por um exemplo de cada SKU.

O script usa APIs públicas, sem credenciais ou scraping de sites de compras.
Por padrão, lê metadados oficiais do Kaggle e pacotes Parquet do espelho Hugging Face.
Isso evita o limite de downloads individuais observado nas APIs do Kaggle e do viewer.
Um HTTP 429 interrompe o processo e preserva o cache, sem repetir em excesso.

Quando acessível, a distribuição original também pode ser usada por arquivo:

```powershell
uv run --locked caixa dataset-rpc --source kaggle
```

Para ampliar a amostra em uma pasta nova:

```powershell
uv run --locked caixa dataset-rpc --output data/rpc-expanded --train-per-class 30 --eval-per-class 10
```

Máximos por execução: 100 referências de treino, 50 exemplos por split de avaliação e
16 downloads simultâneos. Os padrões são 12/4/8.

## Galeria de mercado combinada

Combine os 200 produtos RPC com banana, laranja e pepino da galeria inicial, mantendo
seus SKUs originais e sem substituir `artifacts/gallery.npz`:

```powershell
uv run --locked caixa index --images data/rpc/train data/grocery/train --gallery artifacts/gallery-market.npz
uv run --locked caixa evaluate --images data/rpc/val --gallery artifacts/gallery-market.npz
uv run --locked caixa evaluate --images data/rpc/test --gallery artifacts/gallery-market.npz
```

Isso produz **203 classes e 2.430 referências**. Use somente treino para gerar a galeria;
ajuste limiares em val e reserve test para medir o resultado final. Uma instalação que
não tenha a amostra Grocery pode indexar só `data/rpc/train`, com 200 classes.

Para consultar preços e reconhecer uma foto com a nova galeria:

```powershell
uv run --locked caixa catalog-import data/rpc/catalog.csv
uv run --locked caixa recognize data/minha-foto.jpg --gallery artifacts/gallery-market.npz
```

O MySQL deve estar configurado como no README. A avaliação visual funciona sem banco.
Os comandos Docker equivalentes usam `docker compose run --rm app` no lugar de
`uv run --locked caixa`; após atualizar código, reconstrua a imagem com `docker compose build app`.
O comando `recognize` continua usando a galeria pequena se você não passar `--gallery`.

## Licença e atribuição

O RPC é **CC BY-NC-SA 4.0**, conforme a [página dos autores](https://rpc-dataset.github.io/).
Use esta instalação em pesquisa e testes não comerciais. Os recortes são uma adaptação
e preservam atribuição, origem e licença em `data/rpc/LICENSE-RPC.txt`.
A licença MIT do Grocery Store Dataset não se estende às imagens RPC. Dataset, cache
e galerias ficam fora do Git.

O cabeçalho do espelho contém um rótulo de licença 2.0, mas o texto do próprio espelho
esclarece que não altera a licença original 4.0. Nossa atribuição segue a licença
**CC BY-NC-SA 4.0 declarada pelos autores originais**.

Autores: Xiu-Shen Wei, Quan Cui, Lei Yang, Peng Wang, Lingqiao Liu e Jian Yang.
Artigo: [RPC: A Large-Scale Retail Product Checkout Dataset](https://arxiv.org/abs/1901.07249).
