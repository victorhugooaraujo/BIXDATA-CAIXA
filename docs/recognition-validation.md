# Validação sem cadastro manual — 18/10/2026

Foram executadas consultas reais com DINOv2 na RTX 5060 e OCR local, sem MySQL,
sem preços e sem cadastrar produtos manualmente. A identidade dos produtos vem
dos IDs de treino do RPC. **Há referências do dataset**: isto não é reconhecimento
universal de SKUs sem qualquer catálogo ou referência.

## Protocolo fixado antes do resultado

- Split `test` local do RPC: **800 recortes, 200 SKUs, quatro consultas por SKU**.
- Galeria visual: 12 referências de treino por SKU; OCR: três por SKU.
- DINOv2 ViT-S/14 congelado, sem novo treinamento de pesos nesta etapa.
- OCR PP-OCRv4 mobile chinês/inglês/números; fingerprints com confiança >=0,7.
- Fusão: 80% score visual e 20% textual, sem ajuste após observar o teste.
- Baseline visual: similaridade >=0,75 e margem >=0,05, sem mudar limiares.
- Auditoria por SHA256: 2.400 imagens únicas de treino, 800 consultas únicas,
  nenhuma consulta idêntica ao treino. Isso não substitui deduplicação perceptual.

O split já havia sido usado para medir o baseline visual inicial. Portanto, esta
rodada não é um teste prospectivo cego. Os parâmetros da fusão foram fixados
antes da rodada e não foram retocados com base nestes resultados.

## Produtos conhecidos: todas as 200 classes disponíveis

| Método | Primeira sugestão correta |
| --- | ---: |
| Visual isolado | 389/800 (48,6%) |
| Texto isolado | 168/800 (21,0%) |
| Híbrido | **447/800 (55,9%)** |

O híbrido corrigiu 79 erros visuais e prejudicou 21 acertos: saldo de 58 acertos,
ou **7,25 pontos percentuais**. São acertos de primeira sugestão, não compras
aceitas automaticamente. O ganho é consistente com o observado na validação,
mas o acerto absoluto ainda é insuficiente para cobrança automática.

O gate visual original aceitou 93 imagens: 86 corretas e **7 incorretas**.
A precisão entre aceitas foi 92,5%, com cobertura de apenas 11,6%.
As outras 707 imagens foram rejeitadas. Essas métricas pertencem ao gate visual;
não são uma política de aceitação da fusão.

## Produtos desconhecidos: 20 classes removidas das referências

A seleção foi determinística antes de ler os scores: um SKU a cada dez na lista
ordenada, começando por `rpc-001`, depois `rpc-011`, até `rpc-191`.
As mesmas 800 consultas passam a conter:

- **720 imagens conhecidas**, de 180 SKUs disponíveis na decisão visual/textual.
- **80 imagens desconhecidas**, de 20 SKUs indisponíveis na decisão.

As referências desses 20 SKUs são excluídas do ranking visual; o índice textual
e seu IDF são reconstruídos somente com as 540 referências dos 180 SKUs restantes.
As similaridades visuais são independentes por referência: filtrar classes antes
da decisão preserva os scores que uma galeria física dos 180 SKUs produziria.
O encoder genérico pré-treinado não foi ajustado ao RPC; desconhecido significa
ausente das referências elegíveis, não uma marca jamais vista no pré-treinamento.

| Método | Acerto entre as 720 consultas conhecidas |
| --- | ---: |
| Visual isolado | 359/720 (49,9%) |
| Texto isolado | 151/720 (21,0%) |
| Híbrido | 403/720 (56,0%) |

O gate visual original aceitou 87 imagens, das quais 80 corretas e sete incorretas.
Entre as sete incorretas, **uma era de produto desconhecido**:

- Esperado: `rpc-021`, retirado das referências elegíveis.
- SKU aceito incorretamente: `rpc-019`.
- Consulta: `data/rpc/test/rpc-021/69114.jpg`.

A taxa observada de falsa aceitação de desconhecidos foi **1/80 = 1,25%**.
Nos conhecidos, 634/720 foram rejeitados. A precisão global entre aceitas foi
80/87 (92,0%), e a cobertura global, 10,9%. Rejeitar a maioria das consultas e
aprovar alguns produtos errados não valida uso automático no caixa.

O híbrido continua sem aceitação automática. Sua rejeição não foi validada como
discriminador: retornar revisão para todo mundo, inclusive conhecidos, não prova
capacidade de detectar desconhecidos. Não se deve apresentar isso como rejeição
perfeita nem interpretar o ranking forçado de um desconhecido como reconhecimento.

## Execução e arquivos

Na raiz do projeto:

```powershell
uv sync --project experiments --locked
uv run --project experiments --locked python experiments/cache_ocr.py --images data/rpc/test --workers 4
uv run --project experiments --locked python experiments/validate.py --dataset data/rpc --gallery artifacts/hybrid-rpc-12visual-3text --report artifacts/recognition-open-test-v1.json
```

O relatório JSON local guarda os hashes, SKUs retirados, métricas e resultados
individuais de ambos os cenários. As galerias originais foram preservadas.
O teste demorou 17,17 segundos **com OCR previamente em cache**; isso não inclui
a preparação inicial dos textos, nem representa latência de uma imagem nova.
Pico alocado pelo PyTorch: aproximadamente 120,9 MiB, sem contar desktop/driver/OCR.

Verificação de software: **102 testes passaram e um foi ignorado** por falta de
MySQL de teste. Ruff check/format passaram. Foram corrigidos saída Unicode no
terminal Windows e publicação concorrente de cache, com teste de regressão.

## O que esta rodada comprova

Ela mede reconhecimento dos IDs RPC sem cadastro manual e demonstra ganho do OCR
no ranking. Também encontra uma falsa aceitação de desconhecido sob o gate visual.
Ainda não comprova reconhecimento de qualquer produto brasileiro, de marcas e
gramaturas por atributos, nem de vários itens numa cena. O protocolo usa caixas
verdadeiras; correlação entre recortes de uma mesma cena limita a independência
das amostras. Não há rótulos estruturados confirmados de marca/sabor/tamanho nesta
avaliação, nem um teste independente em câmera real.

A prioridade seguinte é adaptar a representação visual e calibrar rejeição com
conhecidos/desconhecidos em dados de desenvolvimento separados. Esta rodada não
muda limiares nem libera cobranças. Os dados RPC seguem CC BY-NC-SA 4.0.
