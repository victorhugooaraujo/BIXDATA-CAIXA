# Primeiro experimento híbrido — 18/10/2026

Esta etapa implementa a comparação visual/OCR da análise de arquitetura, sem
transformá-la em cobrança automática. O catálogo é gerado dos IDs RPC; não houve
cadastro manual, treinamento de encoder, inclusão de LLM ou troca do baseline.

## Ambiente executado

- Ryzen 7 5700X, 16 GB RAM, RTX 5060 de 8 GB.
- Laboratório isolado com Python 3.12.15 e PyTorch 2.14.1+cu130.
- CUDA 13.0 do wheel; testes reais de matriz e atenção passaram na GPU sm_120.
- RapidOCR 3.10.0, ONNX Runtime 1.31.0 CPU, PP-OCRv4 mobile chinês/inglês/números.
- OCR com dois threads internos por engine; preparação de validação em dois workers.
- Ambiente principal Python 3.15/PyTorch CPU preservado.

Os scripts, dependências e instruções estão em [experiments](../experiments/README.md).
O lockfile desta pasta é independente do principal. O teste CUDA local está em
`artifacts/gpu-doctor-v1.json`; os arquivos de resultados são locais e ignorados pelo Git.

## Protocolo

São 200 SKUs do RPC, com três referências de treino por SKU (600 imagens).
Os três caminhos usam as mesmas referências elegíveis e as mesmas consultas:

1. DINOv2 ViT-S/14 congelado com cosseno máximo por SKU.
2. OCR das referências + TF-IDF de bigramas de caracteres, ajustado só no treino.
3. Fusão linear de 80% de score visual e 20% de score textual, fixada antes da avaliação.

As linhas de OCR com score abaixo de 0,7 não entram no fingerprint textual. Textos,
caixas e scores completos continuam no cache. Quando não há correspondência textual,
a fusão conserva o ranking visual. Score OCR e score de fusão não são probabilidades
de acerto do produto. O texto isolado pode não sugerir candidato.

O índice não utiliza o nome de classe como texto de embalagem. Os nomes genéricos
RPC não são rótulos de marca/sabor/gramatura. Índices e referências têm assinaturas
e hashes; a avaliação recusa uma consulta idêntica a uma referência por SHA256.
Isso não substitui uma auditoria de duplicatas visuais ou sessão de captura.

São recortes com caixas verdadeiras fornecidas pelo dataset, ainda sem detecção
automática. Na primeira rodada, três referências por SKU são usadas em ambos os
ramos. Na segunda, reaproveitamos as 12 referências visuais por SKU já auditadas
no RPC, mantendo três referências por SKU no OCR. Foram excluídas as três classes
Grocery, resultando em 200 classes e 2.400 referências visuais. Dentro de cada
rodada, visual isolado e fusão usam exatamente a mesma galeria visual.

## Resultado

| Referências por SKU | Visual isolado | Texto isolado | Fusão |
| --- | ---: | ---: | ---: |
| 3 visuais / 3 OCR | 247/800 (30,9%) | 173/800 (21,6%) | 318/800 (39,8%) |
| 12 visuais / 3 OCR | 392/800 (49,0%) | 173/800 (21,6%) | 444/800 (55,5%) |

Na rodada com 12 referências visuais, a fusão corrigiu **67 erros** e prejudicou
**15 acertos** visuais: saldo de 52 acertos, ou **6,5 pontos percentuais**.
Na rodada com três referências, corrigiu 81 e prejudicou 10.
Não foram alterados pesos, modelos ou filtros textuais após observar a primeira
rodada; a segunda muda apenas a cobertura visual com a galeria de treino existente.

Os 600 exemplos OCR têm 328 referências com fingerprint textual após o filtro.
Nas consultas, 587/800 imagens tiveram alguma linha detectada, antes do filtro
de confiança. A falta de texto em muitas referências é uma limitação desta rodada.

O pico de memória alocada pelo PyTorch foi 126.725.120 bytes (aproximadamente
120,9 MiB). Isso não é a VRAM total do processo, nem inclui desktop, driver ou OCR.
A rodada completa demorou 12,15 segundos **com OCR previamente em cache**, e a
rodada de três referências, 17,14 segundos. Esses tempos não incluem a preparação
inicial de textos e não são latência de uma imagem nova ponta a ponta.

Arquivos locais: `artifacts/hybrid-rpc-validation-v1.json`,
`artifacts/hybrid-rpc-12visual-validation-v1.json`, e as respectivas galerias
`artifacts/hybrid-rpc-3ref/` e `artifacts/hybrid-rpc-12visual-3text/`.
Os relatórios contêm resultados individuais, textos, caixas, scores e hashes.

Esses números medem **a primeira sugestão em validação**, não precisão de compras
aceitas ou desempenho em produtos desconhecidos. Não houve teste final independente
nesta etapa. Os 55,5% ainda são insuficientes para cobrança automática e não
comprovam, isoladamente, diferenciação por marca, sabor e gramatura.

Verificação de software: **98 testes passaram, 1 foi ignorado** (MySQL sem banco
de teste configurado). Ruff check e format check passaram no repositório definitivo.

## Foto externa de arroz

Na foto enviada anteriormente, o OCR leu `1kg`, com score de linha 0,78287, mas
produziu grafias incorretas para o nome da marca. Isso demonstra leitura de um
atributo e, simultaneamente, uma limitação real do leitor escolhido. O score de
linha não é a probabilidade de aquela embalagem ser o SKU correto.

O arroz brasileiro da foto não faz parte do catálogo RPC. Não foi adicionado à
galeria para forçar acerto. O arquivo `artifacts/rice-ocr-v1.json` guarda a evidência.
Este leitor é um baseline para o dataset chinês; modelos latinos e correção de
orientação mais ampla ainda precisam ser comparados para embalagens brasileiras.

## Limites e próxima decisão

A pipeline híbrida sempre retorna `requires_review=true`, `sku=null` e motivo
`uncalibrated_experiment`. O ranking experimental não consulta preços nem substitui
os comandos normais de reconhecimento. Não há limiar escolhido a partir do teste.

Ainda faltam validação de desconhecidos, calibração, avaliação independente e
rótulos de atributos confirmados. O código não prova que diferencia qualquer
marca, tamanho ou sabor, nem reconhece produtos fora do dataset. Quantidades ainda
são parte do texto bruto: equivalência de unidades e conflitos não têm política
automática. Uma vista sem evidência discriminante continua ambígua.

Após esta comparação, ampliar referências e testar adaptação visual com protocolo
preservado. OCR mais forte ou um reordenador Laya/VLM só deve entrar se corrigir
erros adicionais sem aumentar excessivamente falsas aceitações, memória e latência.
O RPC permanece restrito a pesquisa/testes não comerciais pela CC BY-NC-SA 4.0.
