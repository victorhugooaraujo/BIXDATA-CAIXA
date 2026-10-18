# Laboratório híbrido — separado do baseline

Python 3.12 + PyTorch CUDA 13.0 + RapidOCR/ONNX Runtime CPU, fixados no uv.lock
desta pasta. O projeto principal continua Python 3.15 com PyTorch CPU.

Execute a partir da raiz do repositório no PowerShell:

```powershell
uv sync --project experiments --locked
uv run --project experiments --locked python experiments/doctor.py
uv run --project experiments --locked python experiments/hybrid.py index --dataset data/rpc --gallery artifacts/hybrid-rpc-3ref
uv run --project experiments --locked python experiments/hybrid.py evaluate --dataset data/rpc --gallery artifacts/hybrid-rpc-3ref --split val --report artifacts/hybrid-validation.json
uv run --project experiments --locked python experiments/hybrid.py recognize --gallery artifacts/hybrid-rpc-3ref --image data/minha-foto.jpg --report artifacts/hybrid-photo.json
```

A GPU precisa aceitar os kernels CUDA deste wheel. `doctor.py` testa multiplicação
de matrizes e atenção de verdade. Use `--device cpu` nos experimentos para comparação.
O primeiro uso DINOv2 pode baixar código/pesos; consulte a assinatura fixada no projeto.
RapidOCR usa PP-OCRv4 mobile chinês/inglês/números, deliberadamente explícito para
o RPC. Os modelos podem ser baixados na primeira execução. Isso ainda não é um OCR
universal para todas as embalagens brasileiras.

`index` lê exclusivamente `train/<sku>`, usa até três referências por SKU por padrão
e recusa substituir a galeria existente. Use `--references-per-sku 12` e outro
destino para comparar com todas as referências RPC preparadas. A galeria inclui
os IDs do dataset, dispensando cadastro manual e banco para o experimento.

Os fingerprints textuais são gerados por OCR das mesmas referências visuais;
nenhum nome de classe é usado como se tivesse sido lido. Cache por hash do conteúdo
e versão do OCR preserva textos, caixas e scores. Índices têm assinatura e hashes.
O TF-IDF de bigramas é ajustado só nas referências, e a fusão usa peso textual 0,2
fixado antes da validação. Não é um modelo multimodal treinado ou calibrado.

`evaluate` compara visual isolado, texto isolado e fusão nas mesmas consultas e
galeria. Registra correções/regressões individuais e o pico de alocação CUDA do
PyTorch (não a VRAM total, nem memória de outros processos). Recusa consultar uma
imagem cujo hash também aparece nas referências. O cache pode deixar o tempo de
OCR das repetições menor; os tempos não são um benchmark de produção.

Todos os resultados híbridos têm `requires_review=true`, `sku=null` e razão
`uncalibrated_experiment`. O ranking é experimental; não consulta preços nem aceita
automaticamente compras. O baseline existente e seus limiares não mudaram.

Ainda faltam: calibrar rejeição de desconhecidos, medir pares com atributos
confirmados, avaliar dados novos, adaptar o encoder e comparar modelos concorrentes.
Sem esses passos não há comprovação de precisão para cobrança ou marcas brasileiras.
Não interpretar scores como probabilidade, nem resultados com caixas verdadeiras
como avaliação do detector ou do carrinho completo.
