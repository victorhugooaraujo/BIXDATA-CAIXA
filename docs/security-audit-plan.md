# Auditoria de segurança e prontidão comercial

Data: 26/10/2026. Referência: [plano comercial](production-implementation-plan.md).
Escopo confirmado: um caixa inicial, quatro caixas por loja, quatro lojas e cerca
de 20 mil SKUs. A integração PDV ainda não foi identificada.

## Natureza desta auditoria

Foi feita revisão estática de arquitetura e de arquivos selecionados do protótipo.
Não houve varredura ativa, pentest, certificação, teste de intrusão no PDV ou
avaliação de uma conta RunPod contratada. Os controles abaixo são requisitos a
implementar e evidências a obter, não aprovações já concedidas.

P0/P1 abaixo indicam prioridade de **prontidão para produção**, não uma alegação
de vulnerabilidade explorável do laboratório atual. Nenhum lançamento financeiro
automático foi autorizado por esse planejamento.

## 1. Achados preliminares no repositório

| ID | Evidência observada | Risco ao promover para produção | Tratamento / prioridade |
| --- | --- | --- | --- |
| A01 | `experiments/hybrid.py` retorna revisão; `evaluation.py` marca rejeição híbrida não validada | Atribuir aceitação comercial a uma pipeline que não foi calibrada | Gate de qualidade/risco e contrato de decisão; P0 |
| A02 | CLI e `catalog.py` consultam catálogo, mas não há adapter PDV, ACK ou máquina de estados de item | Duplicação, omissão ou confirmação sonora sem linha incluída | Protocolo persistente e homologação do fornecedor; P0 |
| A03 | Galerias instaladas usam RPC com licença restrita a pesquisa | Uso comercial de referência/dados sem direito apropriado | Auditoria de ativos e substituição por dados licenciados; P0 |
| A04 | `vision.py` carrega código/pesos por `torch.hub.load`, com commit fixado e confiança no upstream | Download/execução no primeiro uso, dependência externa e indisponibilidade | Empacotar código auditado/pesos, hashes e inicialização sem Internet; P1 |
| A05 | `Dockerfile` usa tags e não define usuário; CI usa actions por tag e testes convencionais | Cadeia de fornecimento e isolamento ainda incompletos para exposição comercial | Digests/SHAs, non-root, SBOM, análise de dependências e pipeline de release; P1 |
| A06 | A solução atual é CLI, sem gateway autenticado de produção | A API futura não terá fronteira de autorização por herdar o script | Criar autenticação, validação de schema, quotas e isolamento antes de expor serviço; P0 antes da exposição |
| A07 | Não há política operacional de retenção, dispositivos, incidentes ou auditoria financeira implementada | Privacidade, investigação e recuperação insuficientes | Implementar governança e runbooks; P0 para piloto real |

Pontos positivos observados: `.env`, imagens, pesos e artefatos são ignorados pelo
Git; MySQL do Compose está ligado ao loopback do host; galeria NPZ é aberta com
`allow_pickle=False`; modelo/preprocessamento e artefatos têm verificação de
compatibilidade. Preservar essas propriedades, sem tratá-las como auditoria completa.

## 2. Ativos, confiança e autorização

Ativos: sessão de compra e linhas PDV, identidade do item, catálogo/aliases,
modelos/calibração, evidências de imagem, credenciais, disponibilidade do caixa,
trilha de decisões e infraestrutura GPU/custos.

Fronteiras: câmera/arquivo -> edge; edge -> gateway da loja; gateway -> GPU;
loja -> cloud; ERP -> catálogo; operador -> feedback; pipeline de build -> artefato.
OCR, imagens, saídas do modelo e descrições de catálogos externos são entradas
não confiáveis. Uma resposta JSON válida continua podendo estar errada.

Somente o adapter determinístico tem permissão de propor a inclusão homologada
no PDV. O VLM não recebe função de venda, alteração de preço, SQL livre, shell ou
URLs arbitrárias. Crop e consulta usam IDs de recursos autorizados e resultados
limitados. Isso segue a mitigação de autonomia excessiva e prompt injection da
[OWASP](https://genai.owasp.org/llmrisk/llm01-prompt-injection/) e de
[excessive agency](https://genai.owasp.org/llmrisk/llm062025-excessive-agency/).

## 3. Matriz de ameaças e testes obrigatórios

| Área | Ameaça/cenário | Controle previsto | Evidência para aceite |
| --- | --- | --- | --- |
| Item físico | Embalagem semelhante, tamanho/variante errados, foto de produto, cobertura do rótulo | Captura controlada, atributos obrigatórios por família, rejeição/segunda vista; peso só como evidência auxiliar | Conjunto adversarial e pares difíceis; nenhuma alegação de antifraude universal |
| Contagem | Reentrada, duas unidades iguais, dois itens juntos, mão imóvel | Tracking/evento e fluxo físico; não deduplicar por SKU | Ensaios por unidade e reconciliação independente |
| Rede/PDV | Replay, retry, reordenação, timeout depois de commit, venda encerrada | Chave idempotente persistente, sessão/prazo/loja, ACK e reconciliação | Cada evento validado gera uma linha; eventos expirados não alteram a venda |
| Modelo/ferramenta | Instrução impressa no rótulo, catálogo malicioso, saída forjada | Ferramentas de leitura, permissões no backend e schema; sem ato financeiro pelo modelo | Red team com prompt injection visual/textual e respostas manipuladas |
| Catálogo | SKU inativo, alias errado, troca de preço, loja incorreta, dado externo desatualizado | Importação autenticada, versão, quarentena de conflito, PDV como fonte comercial | Testes de inconsistência e histórico da origem |
| Arquivos | Imagem malformada, arquivo disfarçado, tamanho excessivo, decoder vulnerável | Limites, validar formato real, decoder atualizado e worker isolado | Fuzz/corpus malformado; falha não derruba checkout |
| Acesso | Dispositivo falso, key exposta, consulta a outra loja | Identidade por dispositivo, TLS/mTLS controlado, RBAC, MFA administrativo | Testes negativos e revisão de permissões |
| Cloud/custos | Token roubado, chamadas sem limite, ferramentas recursivas | Credenciais de inferência separadas de administração; quotas, deadline e limite de gasto | Teste de abuso com limites e alertas efetivos |
| Supply chain | Modelo/container adulterado, dependência comprometida | Assinaturas, hashes, digests, SBOM e revisão de código remoto | Rejeitar artefato alterado e reproduzir build |
| Feedback | Correção incorreta/envenenada vira treino | Curadoria, dupla revisão nas famílias críticas, versionamento | Rastrear rótulo -> dataset -> release; rollback |

As imagens não comprovam conteúdo interno nem eliminam fraude de embalagem.
Definir com o varejista qual problema é identificação, qual é prevenção de perdas
e quais situações exigem intervenção humana.

## 4. Segurança por nível

### Local

Disco e credenciais protegidos, usuário de serviço sem privilégios administrativos,
dispositivo identificado, câmera posicionada para evitar rosto/cartão/teclado e
logs sem imagens/base64 por padrão. Captura e PDV separados por permissões. O
botão de contingência deve funcionar sem cloud. Liberar escrita primeiro no
simulador e no PDV de homologação.

### RunPod

Gateway do projeto é o único cliente cloud. Nenhuma chave RunPod no navegador,
aplicação de caixa ou repositório. Administração de GPU/custo é separada da
inferência. Proteger endpoint, Jupyter/SSH, egress e armazenamento. Desabilitar
downloads arbitrários no runtime; pesos chegam pelo processo de release.

Verificar região, retenção, exclusão, suboperadores, tipo de volume e criptografia
efetivamente configurada. Não supor proteção universal por padrão. O
[DPA RunPod](https://www.runpod.io/legal/data-processing-agreement) é material para
avaliação contratual, não prova automática de adequação da implantação.

### Servidor da loja

Segmentar câmera/edge, PDV, administração e backups. Banco e inferência não ficam
abertos à Internet. Manutenção remota por canal autenticado/VPN, identidades por
serviço e princípio de menor privilégio. Criptografar backups e controlar chaves.
Testar UPS, recuperação, falha de disco e perda de nó, incluindo estado do PDV.

Executar containers sem root, com recursos limitados, filesystem somente leitura
quando possível e sem modo privilegiado ou acesso ao socket Docker. O agente de
câmera recebe apenas os dispositivos necessários; workers de modelo não herdam
acesso a todos os dispositivos e credenciais do PDV.

Tráfego sugerido: caixa -> gateway autenticado; gateway -> inferência privada;
adapter -> interface PDV homologada; loja -> gestão/cloud por saída restrita.
Cloud não abre uma rota de acesso direto aos bancos/PDVs das quatro lojas.

## 5. LGPD e privacidade

Imagens com pessoas identificáveis e identificação de operadores podem ser dados
pessoais. Não introduzir reconhecimento facial/biometria; reduzir a captura na
óptica/ROI e cortar antes de enviar para cloud. Aplicar finalidade, necessidade,
segurança e demais princípios da [LGPD](https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm).

Antes do piloto real, jurídico/encarregado e responsáveis do mercado definem base
legal, papéis de controlador/operador, transparência, atendimento de direitos,
contratos e retenção. Não presumir consentimento obrigatório nem um único papel
para varejista e fornecedor. Preparar RIPD como recomendação de projeto, conforme
risco/enquadramento; não afirmar que toda câmera possui obrigação idêntica.

Se houver dados pessoais em infraestrutura estrangeira, avaliar mecanismo de
transferência internacional aplicável e a
[Resolução ANPD 19/2024](https://www.gov.br/anpd/pt-br/acesso-a-informacao/institucional/atos-normativos/regulamentacoes_anpd/resolucao-cd-anpd-no-19-de-23-de-agosto-de-2024).
Preferir recortes minimizados; ausência de rosto não implica anonimização garantida.

Política inicial a aprovar, não prazo legal: não persistir vídeo contínuo; buffer
volátil para captura, TTL curto para recortes de diagnóstico e retenção adicional
somente com finalidade justificada. Separar evidência de disputa, dados de treino
e logs técnicos. TTL, exclusão, backup e acesso precisam ser implementados e testados.

Plano de incidentes define quem avalia risco, preserva evidência e comunica quando
exigido. Considerar os prazos aplicáveis, em regra três dias úteis nos casos
sujeitos à comunicação, com enquadramento confirmado pelo responsável, segundo
o [procedimento ANPD](https://www.gov.br/anpd/pt-br/canais_atendimento/agente-de-tratamento/comunicado-de-incidente-de-seguranca-cis).

O módulo de visão não precisa de PAN/CVV/PIN ou CPF para reconhecer itens.
Pagamento e fiscal permanecem no PDV. O enquadramento PCI ou outros requisitos
depende da integração/topologia reais; não é automaticamente criado nem dispensado
pelo uso de visão. Informação correta ao consumidor segue sendo responsabilidade
da operação; a revisão jurídica inclui os efeitos de SKU/quantidade/preço errados.

## 6. Auditoria de software e release

Usar uma matriz baseada no [OWASP ASVS 5.0](https://asvs.owasp.org/), com controles
selecionados de acordo com a exposição e criticidade, e práticas de desenvolvimento
do [NIST SSDF](https://csrc.nist.gov/pubs/sp/800/218/final). São referências, não
certificação automática nem obrigação legal genérica do protótipo.

Auditar: código/dependências/segredos, imagem e driver, APIs e autorização por loja,
decoder, tratamento de uploads, assinaturas de modelos, backup, logs, pipeline CI,
contrato PDV e ferramentas do VLM. Pin de versão sozinho não substitui atualização
de segurança. Toda exceção tem responsável, prazo e compensação verificável.

Pentest independente antes da inclusão automática em venda, com ambiente e escopo
autorizados. A auditoria inclui eventos duplicados/perdidos, ataques visuais e abuso
de ferramentas, não apenas vulnerabilidades HTTP convencionais.

## 7. Critérios de aprovação e resposta

Antes do gate financeiro: nenhum P0 aberto; vulnerabilidades críticas exploráveis
ou altas no caminho de venda/dados resolvidas; ameaças de fraude restantes
formalmente aceitas pelo varejista. Segurança não certifica a precisão estatística
do modelo: o gate de ML é independente e também precisa passar.

Executar e registrar: perda de WAN/cloud/GPU, crash antes/depois do ACK, pacote
duplicado, troca de sessão, exclusão de imagens, restauração de backup, expiração
de credencial, artefato adulterado e rollback completo. Ensaiar com operador e PDV.

Runbook de incidente: desativar o escopo automático, manter contingência, reconciliar
eventos incertos com o PDV, preservar apenas evidências necessárias, restaurar
pacote anterior e apurar vendas afetadas. Sem replay financeiro de fila de imagens.

Entregáveis de auditoria: inventário e diagrama de confiança, matriz de controles,
relatório de achados, evidências, reteste, plano de tratamento e aprovação assinada
pelos donos de operação, engenharia e segurança/privacidade. Nada disso foi marcado
como concluído nesta etapa de planejamento.
