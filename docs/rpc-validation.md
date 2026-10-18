# Instalação e validação RPC — 18/10/2026

Instalação local em `C:\Users\hugoa\OneDrive\Documentos\projetinho\data\rpc`.
Python 3.15.0, PyTorch 2.14.1 CPU e PyArrow 26.0.0.

## Dados instalados

- **200 produtos em 17 grupos**, com prefixos `rpc-001` a `rpc-200`.
- **4.000 recortes**: 2.400 de treino, 800 de validação e 800 de teste.
- Por SKU: 12 referências de treino e 4 exemplos em cada split de avaliação.
- 3.829 imagens-fonte distintas utilizadas nos recortes.
- Aproximadamente **254 MB** de dataset preparado, incluindo anotações.
- Aproximadamente **10,72 GB** de cache, incluindo originais selecionados e Parquet.
- **23 pacotes Parquet**: 19 de treino, 1 de validação e 3 de teste.
- Conjunto candidato: 53.739 imagens oficiais de treino, 2.000 de validação e 6.546 de teste.

O download por arquivo do Kaggle e a API de imagens do viewer atingiram limites de
requisições. A instalação foi concluída pelos pacotes Parquet públicos, fixados no
commit do espelho registrado no manifesto, com checksums SHA256 publicados pelo Hub.
Anotações seguem o RPC oficial v5; classes, caixas e dimensões do espelho foram
conferidas antes do uso. Imagens oficiais já presentes no cache foram reutilizadas.

O manifesto, os nomes originais e a atribuição estão dentro de `data/rpc`.
`preview.html` mostra uma referência de treino por produto. O cache Parquet permite
ampliar o dataset; a galeria pronta e os recortes permitem testar sem reler esses pacotes.

## Verificação executada

- **87 testes passaram; 1 skipped** (MySQL sem `TEST_DATABASE_URL`).
- Ruff check e format check passaram no repositório final.
- Os 4.000 JPEGs preparados têm formato RGB e lado máximo de 512 pixels.
- SHA256 de todos os recortes foi conferido contra o manifesto.
- Contagens por SKU e split e ausência de sobreposição de arquivos-fonte foram conferidas.
- Uma inspeção visual de salgadinho, bebida, higiene e papelaria confirmou os recortes.
- A galeria original continua com o mesmo SHA256, preservando os testes anteriores.

## Avaliação da galeria combinada

A galeria de mercado contém **203 classes e 2.430 referências**: RPC mais as três
classes da demonstração Grocery. Usa DINOv2 congelado e os limiares iniciais de
similaridade 0,75 e margem 0,05. Os pesos não são ajustados e as imagens de avaliação
não entram na galeria. A extração local usa quatro threads de CPU.

| Split | Imagens | Primeira sugestão correta | Aceitos | Corretos entre aceitos | Revisão |
| --- | ---: | ---: | ---: | ---: | ---: |
| val | 800 | 392/800 (49,0%) | 101 (12,6%) | 97/101 (96,0%) | 699 |
| test | 800 | 389/800 (48,6%) | 93 (11,6%) | 86/93 (92,5%) | 707 |

Os limiares não foram ajustados após observar esses resultados. No teste houve
**7 aceitações incorretas**, e a maioria das imagens foi encaminhada para revisão.
Esse é um baseline do extrator congelado com 12 referências por SKU, não um resultado
suficiente para cobrança automática. Melhorar a primeira sugestão exige investigar
referências, representação e o cenário de câmera; alterar só o limiar não corrige
os casos em que a primeira classe sugerida está errada.

Os resultados completos, com cada predição e a assinatura da galeria, estão em
`artifacts/rpc-market-validation.json`. Os hashes e contagens da auditoria estão em
`artifacts/rpc-installation-audit.json`.

Este é um protocolo de **classificação com caixas verdadeiras**, não um detector de
objetos ou uma avaliação de checkout completo. Os recortes de cenas podem conter
oclusões e vizinhos. A amostra de avaliação vem de pacotes iniciais suficientes para
cobrir todas as classes e não representa uniformemente todo o benchmark oficial.
O dataset de produtos chineses não substitui referências dos SKUs brasileiros reais.

O uso dos dados segue **CC BY-NC-SA 4.0**, para pesquisa e testes não comerciais.
