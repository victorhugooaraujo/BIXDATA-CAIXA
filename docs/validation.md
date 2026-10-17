# Validação local — 16/10/2026

Executada em Windows amd64, Python **3.15.0**, uv **0.13.1** e PyTorch **2.14.1+cpu**.

- `uv sync --python 3.15.0`: ambiente instalado e `uv.lock` gerado.
- Ruff check e format check: passaram.
- Pytest: **63 passaram; 1 skipped** (integração MySQL sem `TEST_DATABASE_URL`).
- Download real: **60 imagens** e metadados oficiais, sem clone completo.
- DINOv2 real: código e pesos oficiais baixados; galeria criada com **30 imagens de train**.
- Inferência CPU real executada em **val** e **test**, preservando os splits oficiais.

Configuração: classes 6 (Banana), 16 (Orange), 63 (Cucumber); 10 imagens de treino por
classe e 5 de cada split de avaliação por classe. Código upstream fixado nos SHAs
registrados em `dataset.py` e `vision.py`. Limiares iniciais: similaridade **0,75** e
margem **0,05**. Não foram ajustados após observar o teste.

| Split | Imagens | Primeira sugestão correta | Aceitos automaticamente | Corretos entre aceitos | Revisão |
| --- | ---: | ---: | ---: | ---: | ---: |
| val | 15 | 15/15 (100%) | 15 (100%) | 15/15 (100%) | 0 |
| test | 15 | 13/15 (86,7%) | 11 (73,3%) | 11/11 (100%) | 4 |

Esses resultados comprovam o fluxo de extração e comparação neste subset, com três
classes visualmente diferentes. Não demonstram desempenho em um supermercado real,
separação de SKUs parecidos ou rejeição confiável de produtos desconhecidos.
Precisamos de mais dados e negativos para avaliar esses casos.

**Limitação de ambiente:** Docker/Compose e servidor MySQL não estavam disponíveis nesta
máquina. O build Docker e o teste contra MySQL real não foram executados localmente.
A CI inclui MySQL 8.4 e `TEST_DATABASE_URL`, mas ainda precisa ser executada no GitHub.
Os testes SQLite verificam lógica do catálogo e integração da CLI, não substituem
a validação do backend MySQL.

Os avisos upstream de xFormers desabilitado são esperados no modo CPU usado.
Os dados, pesos e galeria ficam ignorados pelo Git. Os arquivos gerados acompanham a
pasta local do protótipo para repetir a avaliação; instalações novas podem reproduzi-los
pelos comandos do README.

Na cópia final, os 63 testes e a avaliação de test foram repetidos com o mesmo resultado.
O diretório temporário padrão do Windows apresentou bloqueio de permissão; os testes
passaram usando uma pasta temporária nova dentro de `.cache`. Se isso ocorrer na sua
sessão, execute `uv run --locked pytest --basetemp .cache/pytest-local`.
