# Backlog e marcos — scanner visual de caixa

Base: [plano comercial](production-implementation-plan.md) e
[segurança](security-audit-plan.md), 26/10/2026.

Cada item abaixo deve virar uma entrega pequena e revisável. Quando houver código,
usar Conventional Commits, PR, testes proporcionais e pacote de release reproduzível.
O modelo, o contrato PDV e a evidência de qualidade precisam evoluir juntos.

## Ciclo inicial: duas semanas de descoberta e bancada

| ID | Entrega | Critério de pronto | Responsável principal |
| --- | --- | --- | --- |
| D01 | Identificar PDV/ERP, fornecedor, versão e opções de integração | Documentação de consulta/inclusão/ACK/reconciliação e ambiente de teste disponíveis | Backend + mercado |
| D02 | Exportar catálogo e vendas por item, sem dados de cliente desnecessários | Amostra auditada com SKU, aliases, tamanho/variante, unidade, disponibilidade por loja e giro | Dados + operação |
| D03 | Medir ritmo real do caixa | Distribuição de itens/min, picos/rajadas e tempo de leitura do scanner, em turnos representativos | QA + operação |
| D04 | Definir escopo e orçamento de risco | Documento de erro aceitável, cobertura total, exceções e metas assinado pelo mercado | Produto + operação |
| D05 | Desenhar captura física | Comparação de uma/duas câmeras, iluminação, reflexo, oclusão e área útil; checklist de privacidade | Visão + hardware |
| D06 | Inventariar dados/modelos e permissões | Origem, licença comercial, retenção e tratamento cloud identificados | Segurança + dados |
| D07 | Criar matriz de teste das 77 fotos | Item alvo e atributos verificados, agrupados por item/vista; sem usar rótulo do modelo como verdade | QA + operação |
| D08 | Propor setup RunPod e limites de experimento | Imagem/modelo fixados, custo estimado, credenciais e aprovação de contratação definidos | Plataforma |

D01 é dependência do piloto com escrita. Se não houver ACK/idempotência ou
reconciliação confiável, continuar apenas em sombra e resolver com o fornecedor.

## Épico E1 — contrato e simulador de caixa

| Entrega sugerida | Aceite |
| --- | --- |
| `feat(events): add item lifecycle and durable journal` | Estado por apresentação física, retomada de crash, prazo e sessão |
| `feat(pdv): add simulator with idempotency and acknowledgement` | Retry retorna a mesma linha; pedido tardio/cancelado não inclui item |
| `feat(capture): add stable item trigger and quality checks` | Vazio/múltiplos itens/imagem ruim recusados; duas unidades iguais funcionam como dois eventos |
| `test(pdv): cover uncertain commit and reconciliation` | Queda depois do commit não gera nova unidade; erro não emite confirmação |

Contratos iniciais de API, versionados e autenticados:

| Rota lógica | Quem chama | Limite de autoridade |
| --- | --- | --- |
| `POST /v1/item-events` | Agente do caixa | Cria evento físico associado à sessão |
| `POST /v1/inference/fast` | Roteador | Retorna candidatos/evidências, não venda |
| `POST /v1/inference/expert` | Roteador | Exceção com prazo, tokens e ferramentas limitados |
| `GET /v1/catalog/snapshots/{version}` | Serviços autorizados da loja | Leitura de catálogo do escopo permitido |
| `POST /v1/pdv/commands` | Motor de decisão autorizado | Comando idempotente; bloqueado a modelos/ferramentas |
| `GET /v1/pdv/commands/{id}` | Adapter/roteador | Estado autoritativo ou reconciliação da inclusão |
| `POST /v1/operations/vision-mode` | Operador/supervisor conforme papel | Alterna modo e audita; sem credencial cloud |

Os nomes são proposta de interface interna, não endpoints já existentes. O contrato
financeiro final será adaptado à API/SDK do PDV, sem bypass de regras fiscais.

## Épico E2 — identidade comercial e dados

- Migrar schema do catálogo para aliases, famílias, atributos, unidade de venda,
  disponibilidade por loja e versões. Preço final continua no PDV.
- Importação inicial e incremental do ERP, com histórico/quarentena de conflitos.
- Importar imagens/metadados com direitos de uso e revisão de qualidade.
- Capturar 300–500 SKUs iniciais de giro medido e seus vizinhos difíceis.
- Construir splits por tempo/sessão/loja, unknowns e pares de tamanho/variante.
- Definir admissão/retirada de SKU da allowlist; nenhuma promoção automática por
  feedback não revisado ou por confiança autorreferida do modelo.

Aceite: dataset rastreável, catálogo consistente e teste reservado; relatório de
cobertura sobre as vendas reais, incluindo itens não elegíveis.

## Épico E3 — comparação de reconhecimento no RunPod

Mesmas consultas e referências elegíveis em quatro candidatos: VLM direto;
localização + VLM; especialista + OCR; especialista + VLM seletivo.

Entregas: runner de avaliação, contratos de ferramentas de leitura, localização
do produto, extração com evidência, resolução SKU e calibração por família/risco.
Registrar p50/p95/p99 ponta a ponta, qualidade, custo e memória. Revalidar qualquer
quantização, exportação, distilação ou troca de resolução.

Aceite: selecionar a menor combinação que alcance o gate do estágio. Se nenhuma
alcançar, ajustar captura/dados/escopo; não liberar por aumento de threshold isolado.

## Épico E4 — gateway, roteamento e contingência

Implementar deadline propagado, seleção local/LAN/cloud por capacidade/saúde,
backpressure, circuito aberto, limite por caixa/loja e cancelamento de resultados
obsoletos. Não encadear retries sem orçamento de tempo.

Aceite: apresentação expirada nunca escreve na venda; perda de WAN mantém operação
homologada local ou contingência explícita; evento com commit incerto é reconciliado
antes de novo lançamento. Latência e quotas testadas em 2x o pico de projeto.

## Épico E5 — servidor e produção

Dois domínios de falha ou redundância equivalente por loja; capacidade sobrevivente
homologada no pico. Catálogo/pacote local, health checks com inferência real,
certificados, segredos, backup/restauração e telemetria de evento.

CI/CD: build assinado, artefatos por hash, contrato/segurança/qualidade/carga como
gates, canary por caixa e rollback do pacote de decisão. Sem download dinâmico de
código no runtime comercial. Nunca expor banco ou GPU diretamente ao PDV/browser.

Aceite: exercício de rede/GPU/servidor/energia, retomada financeira, pentest e
rollback passam com operador presente; nenhuma meta é declarada só por diagrama.

## Marcos de liberação

| Marco | Permissão operacional | Evidência mínima |
| --- | --- | --- |
| M0 — bancada | Sem acesso a venda real | Simulador e interfaces de captura/catálogo |
| M1 — sombra | IA não inclui item | Comparação por evento em turnos e condições reais |
| M2 — assistido | Operador confirma cada sugestão | Qualidade/tempo/intervenção medidos, PDV homologado |
| M3 — restrito | Automação em allowlist num caixa | Gate estatístico inicial, segurança e risco aprovados |
| M4 — loja | Quatro caixas, escopo aprovado | Pico/contingência e estabilidade sem regressão |
| M5 — franquia | Expansão gradual a quatro lojas | Generalização por loja, cobertura e alvo amplo demonstrados |

PRs/commits entregam capacidades pequenas; marcos de produção exigem o pacote
integrado. Não declarar que um teste unitário de deduplicação comprova a contagem
física, nem que uma média de OCR comprova identidade comercial.

## Decisões pendentes para fechar contratação e calendário

Fornecedor/SDK PDV; catálogo de 20 mil por franquia ou por loja; mistura de pesáveis
e embalados; fluxo físico; câmeras; operadores envolvidos; conectividade e latência
real; janela de manutenção; direitos dos dados; orçamento de erro; equipe; custos
de hardware/cloud; suporte e responsabilidade por incidente.

Nenhuma compra/instância paga ou ativação em venda real faz parte desta entrega
de planejamento. As aprovações futuras devem se referir à configuração e ao risco
concretos do marco, com evidência revisável.
