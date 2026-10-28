# Demonstração pelo celular

Site: **https://bixdata-caixa-demo.vercel.app**

O visual segue o HTML fornecido, incluindo logo, vermelho/amarelo, área de captura
e cupom. O modelo continua experimental: esta entrega muda a interface e o acesso,
não demonstra precisão comercial nem amplia o conjunto de produtos reconhecíveis.

## Usar no celular

1. Abra o endereço no Chrome ou Safari e cole o código de acesso fornecido no chat.
2. Toque em **Tirar foto e reconhecer** para usar a câmera nativa do celular, ou em
   **Abrir câmera ao vivo** e permita o acesso solicitado pelo navegador.
3. Fotografe uma embalagem centralizada, confira os candidatos e o OCR. Corrija
   pelo catálogo demonstrativo se necessário e confirme uma unidade.
4. Confira a linha no cupom. **Finalizar demonstração** encerra apenas a sessão simulada.

Todos os preços são fictícios, de R$ 1,00. Não há cobrança, pagamento, documento
fiscal ou integração com o estoque do mercado. A similaridade visual não representa
uma probabilidade calibrada de acerto. Se o produto não pertencer às 211 classes
atuais, o primeiro candidato pode estar errado; a confirmação humana é obrigatória.

Se a câmera for negada, use a captura nativa ou a galeria. JPEG/PNG são convertidos
para JPEG de até1600px e1,5MB antes do envio. Alguns navegadores não decodificam HEIC:
nesse caso, tire outra foto pela captura nativa ou escolha JPEG. Fotos não são enviadas
automaticamente enquanto a câmera está aberta; é necessário capturar.

## Infraestrutura instalada

```text
Celular HTTPS
    → Vercel: frontend e gateway autenticado
    → Cloudflare Quick Tunnel HTTPS
    → PC, porta8766 no loopback: modelo CUDA + OCR
    → resultado para revisão e ACK do cupom simulado
```

Projeto Vercel `bixdata-caixa-demo`, na equipe `victor-e126`. Somente frontend e
gateway foram enviados; fotos do conjunto, pesos e banco continuam locais.
Nenhuma porta foi aberta no roteador. O túnel é uma conexão de saída do PC.
As fotos de teste passam pelos serviços Vercel/Cloudflare e são processadas no PC.
O navegador recebe um cookie HttpOnly/Secure de oito horas após validar o código.
O token da ponte e a chave de assinatura ficam somente na configuração privada
local e nas variáveis sensíveis da Vercel. Não entram no JavaScript público ou Git.

**Este PC precisa ficar ligado, acordado e com Internet.** A demonstração já foi
iniciada em segundo plano. Não é necessário executar comandos para testar agora.

## Ligar ou desligar a ponte

Na pasta do projeto, para retomar um backend parado:

```powershell
.\start-mobile-backend.ps1
```

Para encerrar a conexão móvel:

```powershell
.\stop-mobile-backend.ps1
```

O Quick Tunnel é temporário e muda de endereço quando seu processo reinicia
(por exemplo, após reiniciar o Windows). Se isso acontecer, o script informa que
é necessário **pedir ao assistente para reativar o link da demonstração**. Ele pode
ler a nova configuração privada em `.cache/mobile-bridge.json`, atualizar apenas
`BACKEND_URL` no projeto Vercel e republicar os mesmos arquivos. Não publique esse
arquivo e não copie seu conteúdo para o chat. Uma instalação permanente precisa
de um túnel nomeado/domínio ou backend hospedado; isso ficou fora desta PoC.

Nenhum serviço de inicialização do Windows ou ajuste de energia foi instalado.
Esta ponte de apresentação não tem SLA nem a disponibilidade prevista no plano comercial.

## Desenvolvimento e verificação

Frontend sem dependências externas, em `frontend/public`. Gateway Node24 em
`frontend/api` e `frontend/lib`, com testes usando `node:test`. Backend preserva
o modo local normal na porta8765; o modo remoto exige token em toda requisição e
permite apenas hosts locais/Quick Tunnel. API/documentação HTML locais não são
expostas pelo modo remoto.

```powershell
npm test --prefix frontend
uv run --locked pytest
```

Regressões: autenticação/cookie, expiração, Origin, rota/SSRF, upload/deadline,
PC indisponível, compatibilidade do rewrite real da Vercel, limites de imagem,
seleção, cupom, fechamento idempotente e retomada de sessão fechada.

O consentimento e funcionamento da câmera física do celular devem ser conferidos
no aparelho do usuário; testes de navegador no computador não comprovam isso.

Referências: [câmera em contexto seguro](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia),
[Quick Tunnels para testes](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/),
[Vercel Node Functions](https://vercel.com/docs/functions/runtimes/node-js).
