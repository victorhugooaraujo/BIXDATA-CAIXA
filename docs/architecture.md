# Decisão do protótipo

O objetivo inicial é verificar se características visuais pré-treinadas distinguem alguns produtos
em imagens com um item dominante. A interface inicial é uma CLI, que pode receber arquivos de uma
câmera futuramente. Não há cobrança, controle fiscal, contagem, detector de objetos ou captura
contínua nesta versão.

1. Baixar subset rastreável do Grocery Store Dataset com splits oficiais separados.
2. Extrair vetores das imagens de **train** com DINOv2 ViT-S/14 congelado.
3. Guardar esses vetores, SKUs e assinatura de modelo/pré-processamento numa galeria `.npz`.
4. Extrair vetor de uma nova imagem e comparar por similaridade de cosseno.
5. Aceitar somente se o melhor SKU superar similaridade e margem mínimas entre classes.
6. Consultar nome e preço pelo SKU no MySQL. SKU sem catálogo retorna revisão, sem preço.

A galeria usa o melhor exemplo de cada classe para fazer a comparação. Múltiplas referências
do mesmo SKU não são tratadas como classes concorrentes. Uma galeria com somente uma classe
pede revisão, pois não permite comparar com outro produto.

Esse cadastro de exemplos substitui um treinamento supervisionado caro nesta primeira etapa.
Os pesos DINOv2 não são ajustados. Usar **val** para escolher limiares e **test** uma vez para
medir o resultado final; não misturar essas imagens na galeria. Similaridade não é uma
probabilidade de acerto. Os limiares iniciais 0,75/0,05 são heurísticos e não garantem rejeição
de produtos desconhecidos. Antes de qualquer cobrança automática são necessárias imagens
reais do caixa, negativos, calibração e validação por SKU.

O dataset demonstra categorias de alimentos, não o catálogo exato de um supermercado brasileiro.
Embalagens quase idênticas, tamanhos, sabores e marcas exigirão referências próprias. Preço
é um dado do catálogo e nunca é inferido da imagem.

Python 3.15.0 e PyTorch 2.14.1 CPU são fixados no projeto. Os wheels Python 3.15 do PyTorch
vêm do [índice oficial](https://download.pytorch.org/whl/cpu), declarado explicitamente no uv.
Executamos em modo eager; `torch.compile` ainda não é suportado nessa combinação segundo o
[release oficial](https://pytorch.org/blog/pytorch-2-14-release-blog/).
O [DINOv2 oficial](https://github.com/facebookresearch/dinov2) é carregado em um commit fixo;
o primeiro uso baixa código e pesos. PyTorch Hub executa esse código upstream. O cache permite
reutilizar os pesos em execuções seguintes. A galeria rejeita metadados incompatíveis para evitar
misturar vetores gerados por configurações diferentes.

MySQL 8.4 mantém só o catálogo de preços desta versão. Embeddings ficam em arquivo local.
Migrações, histórico de vendas e armazenamento vetorial podem ser adicionados quando o fluxo
com câmera e dados reais estiver validado.
