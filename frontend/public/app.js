import {fitDimensions, selectedProduct, resolveSelection, receiptSummary, requestJson, describeError} from './mobile-core.mjs';

const $ = id => document.getElementById(id);
const money = value => (value/100).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});
let catalog = [], pending = null, selected = null, session = null;
let busy = false, ready = false, stream = null, previewImage = null, audio = null;
try { session = sessionStorage.getItem('bixdata-demo-session'); } catch {}

function message(text,error=false){
  $('feedback').textContent=text;
  $('feedback').className='feedback'+(error?' error':'');
}
function controls(value){
  busy=value;
  for(const id of ['capture','upload','openCamera','samples','done','discard','search']) {
    $(id).disabled=value||!ready;
  }
  $('done').disabled=value||!ready||!Number($('done').dataset.count);
  $('confirm').disabled=value||!ready||!pending||!selected;
  $('stage').classList.toggle('busy',value);
  for(const button of document.querySelectorAll('.candidate')) button.disabled=value;
}
function lockScreen(){
  stopCamera();
  ready=false;
  $('workspace').hidden=true;
  $('access').hidden=false;
  $('connection').textContent='Acesso protegido';
  $('connection').className='connection off';
}
async function call(path,options={}){
  const controller=new AbortController();
  const timer=setTimeout(()=>controller.abort(),65000);
  try{return await requestJson('/api'+path,{...options,signal:controller.signal});}
  catch(error){if(error.status===401)lockScreen();throw error;}
  finally{clearTimeout(timer);}
}
const post=(path,body={})=>call(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});

async function refreshReceipt(){
  const receipt=await call(`/sessions/${session}/receipt`);
  const result=receiptSummary(receipt);
  $('items').replaceChildren();
  if(!result.count){
    const empty=document.createElement('p');empty.className='empty';
    empty.textContent='Nenhuma unidade confirmada. Apresente o primeiro produto.';
    $('items').append(empty);
  }
  for(const item of result.lines){
    const row=document.createElement('div');row.className='item';
    const name=document.createElement('b');name.textContent='1 × '+item.name;
    const price=document.createElement('span');price.className='price';price.textContent=money(item.price_cents);
    const note=document.createElement('small');note.textContent='Preço fictício · unidade confirmada';
    row.append(name,price,note);$('items').append(row);
  }
  $('count').textContent=result.count+(result.count===1?' item':' itens');
  $('total').textContent=money(result.total);
  $('done').dataset.count=String(result.count);
  $('done').disabled=busy||!result.count;
  return Boolean(receipt.closed);
}
function rememberSession(){
  try{sessionStorage.setItem('bixdata-demo-session',session);}catch{}
  $('sessionLabel').textContent='Sessão de demonstração '+session.slice(0,8);
}
async function createSession(){
  session=(await post('/sessions')).session_id;
  rememberSession();await refreshReceipt();
}
async function loadApp(){
  $('access').hidden=true;$('workspace').hidden=false;
  ready=false;controls(true);message('Conectando ao PC de processamento…');
  try{
    await call('/health');
    catalog=await call('/catalog');
    if(!Array.isArray(catalog))throw Error('Catálogo demonstrativo indisponível.');
    const samples=await call('/samples');
    $('samples').replaceChildren(new Option('Escolha uma foto…',''));
    for(const item of samples)$('samples').append(new Option(`${item.id} · ${item.name}`,item.id));
    if(session){
      try{if(await refreshReceipt())await createSession();else rememberSession();}
      catch(error){if(error.status===409||error.status===404)await createSession();else throw error;}
    }else await createSession();
    ready=true;
    $('connection').textContent='PC conectado · demonstração';
    $('connection').className='connection';
    message('Pronto. Centralize uma embalagem ou escolha uma foto.');
  }catch(error){
    $('connection').textContent='PC indisponível';$('connection').className='connection off';
    message(describeError(error)+' Toque em “Reconectar” para tentar novamente.',true);
    $('reconnect').hidden=false;
  }finally{controls(false);}
}

function stopCamera(){
  if(stream)stream.getTracks().forEach(track=>track.stop());
  stream=null;$('video').srcObject=null;$('video').hidden=true;
  $('stopCamera').hidden=true;$('openCamera').textContent='Abrir câmera ao vivo';
  $('preview').hidden=!previewImage;
  $('stageMessage').hidden=Boolean(previewImage);
  $('guide').hidden=Boolean(previewImage);
}
async function openCamera(){
  stopCamera();
  if(!window.isSecureContext||!navigator.mediaDevices?.getUserMedia){
    message('Câmera ao vivo indisponível neste navegador. Use “Tirar foto e reconhecer” para abrir a câmera do celular.',true);
    return;
  }
  try{
    stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:'environment'},width:{ideal:1920},height:{ideal:1080}},audio:false});
    $('video').srcObject=stream;await $('video').play();
    $('video').hidden=false;$('preview').hidden=true;$('stageMessage').hidden=true;
    $('guide').hidden=false;$('stopCamera').hidden=false;
    message('Posicione o produto no centro e toque em “Tirar foto e reconhecer”.');
  }catch{
    stopCamera();
    message('Acesso à câmera negado ou indisponível. Use “Tirar foto e reconhecer” ou “Escolher foto”.',true);
  }
}
function canvasBlob(canvas,quality){
  return new Promise((resolve,reject)=>canvas.toBlob(blob=>blob?resolve(blob):reject(Error('Não foi possível preparar a foto.')),'image/jpeg',quality));
}
async function preparePhoto(file){
  if(!file?.size)throw Error('A foto está vazia. Capture novamente.');
  if(file.size>40_000_000)throw Error('Foto muito grande para preparar no celular. Envie uma imagem de até 40 MB.');
  let image;
  try{image=await createImageBitmap(file,{imageOrientation:'from-image'});}
  catch{
    const url=URL.createObjectURL(file);
    try{image=new Image();image.src=url;await image.decode();}
    catch{throw Error('Este navegador não conseguiu abrir a foto. Envie JPEG/PNG ou tire uma nova foto pela câmera.');}
    finally{URL.revokeObjectURL(url);}
  }
  const size=fitDimensions(image.width,image.height);
  const canvas=document.createElement('canvas');Object.assign(canvas,size);
  canvas.getContext('2d').drawImage(image,0,0,size.width,size.height);
  image.close?.();
  let blob;
  for(const quality of [.88,.72,.55]){
    blob=await canvasBlob(canvas,quality);
    if(blob.size<=1_500_000)return blob;
  }
  throw Error('A foto continua acima do limite. Tente capturar outra imagem com menos detalhes de fundo.');
}
async function preview(blob){
  previewImage?.close?.();
  try{previewImage=await createImageBitmap(blob);}
  catch{
    const url=URL.createObjectURL(blob);
    try{previewImage=new Image();previewImage.src=url;await previewImage.decode();}
    finally{URL.revokeObjectURL(url);}
  }
  $('preview').hidden=false;$('video').hidden=true;$('guide').hidden=true;
  $('stageMessage').hidden=true;drawPreview();
}
function drawPreview(box=null){
  if(!previewImage)return;
  const canvas=$('preview');
  canvas.width=previewImage.width;canvas.height=previewImage.height;
  const context=canvas.getContext('2d');context.drawImage(previewImage,0,0);
  if(box){
    context.strokeStyle='#ffd500';context.lineWidth=Math.max(3,canvas.width/180);
    context.strokeRect(box[0]*canvas.width,box[1]*canvas.height,(box[2]-box[0])*canvas.width,(box[3]-box[1])*canvas.height);
  }
}
function choose(sku,{automatic=false}={}){
  const product=resolveSelection(sku,catalog,{busy,automatic});
  if(product===undefined)return;
  selected=product;
  $('selection').textContent=selected?'Selecionado: '+selected.name:'Selecione um produto para confirmar.';
  for(const button of document.querySelectorAll('.candidate'))button.classList.toggle('chosen',button.dataset.sku===sku);
  $('confirm').disabled=busy||!pending||!selected;
}
function candidateButton(product,similarity=null){
  const button=document.createElement('button');button.type='button';button.className='candidate';button.dataset.sku=product.sku;
  const name=document.createElement('span');name.textContent=product.name;
  const detail=document.createElement('small');detail.textContent=product.sku+' · preço fictício '+money(product.price_cents);
  name.append(detail);button.append(name);
  if(Number.isFinite(similarity)){
    const score=document.createElement('span');score.className='similarity';score.textContent='Sim. '+similarity.toFixed(3);button.append(score);
  }
  button.onclick=()=>choose(product.sku);return button;
}
function showResult(result){
  pending=result.event_id;selected=null;$('result').hidden=false;
  $('analysisTime').textContent=Number.isFinite(result.seconds)?`${result.seconds.toFixed(2)} s de processamento · revisão obrigatória`:'Revisão obrigatória';
  const crop=typeof result.crop==='string'&&result.crop.startsWith('data:image/jpeg;base64,')?result.crop:null;
  $('crop').hidden=!crop;if(crop)$('crop').src=crop;
  $('ocr').textContent=result.ocr?.join('\n')||'Nenhum texto legível ou OCR indisponível.';
  $('candidates').replaceChildren();$('catalogResults').replaceChildren();$('search').value='';
  for(const candidate of result.candidates||[]){
    const product=selectedProduct(candidate.sku,catalog);
    if(product)$('candidates').append(candidateButton(product,candidate.similarity));
  }
  const note=result.reason==='reposition'?'Produto não localizado. Reposicione e tire outra foto. A seleção manual continua disponível.':result.reason==='unknown'?'Reconhecimento incerto. Confira os candidatos ou procure o produto no catálogo.':'A sugestão pode estar errada. Confira marca, variante e tamanho antes de confirmar.';
  $('reviewNote').textContent=note;drawPreview(result.box);
  choose(result.sku||null,{automatic:true});
  message(result.reason==='reposition'?'Reposicione a embalagem para uma nova tentativa.':'Resultado disponível. Revise antes de confirmar.');
}
async function recognize(file){
  if(busy||!ready)return;
  controls(true);pending=null;selected=null;$('result').hidden=true;
  stopCamera();message('Preparando foto e reconhecendo no PC…');
  try{
    const blob=await preparePhoto(file);await preview(blob);
    const form=new FormData();form.append('session_id',session);form.append('event_id',crypto.randomUUID());form.append('image',blob,'capture.jpg');
    const result=await call('/events',{method:'POST',body:form});
    showResult(result);
  }catch(error){message(describeError(error),true);}
  finally{controls(false);}
}
function prepareAudio(){
  try{const Audio=window.AudioContext||window.webkitAudioContext;if(!Audio)return;audio??=new Audio();audio.resume().catch(()=>{});}catch{}
}
function beepAfterAck(){
  if(!audio)return;
  try{const tone=audio.createOscillator(),volume=audio.createGain();tone.frequency.value=1050;volume.gain.value=.07;tone.connect(volume).connect(audio.destination);tone.start();tone.stop(audio.currentTime+.12);}catch{}
}

$('accessForm').onsubmit=async event=>{
  event.preventDefault();$('unlock').disabled=true;$('accessMessage').textContent='Verificando acesso…';
  try{await post('/access',{code:$('accessCode').value});$('accessCode').value='';$('accessMessage').textContent='';await loadApp();}
  catch(error){$('accessMessage').textContent=error.status===401?'Código inválido. Confira o código fornecido para esta demonstração.':describeError(error);}
  finally{$('unlock').disabled=false;}
};
$('openCamera').onclick=openCamera;$('stopCamera').onclick=stopCamera;
$('upload').onclick=()=>$('galleryFile').click();
for(const id of ['cameraFile','galleryFile'])$(id).onchange=event=>{const file=event.target.files[0];event.target.value='';if(file)recognize(file);};
$('capture').onclick=async()=>{
  if(busy||!ready)return;
  if(!stream||!$('video').videoWidth){$('cameraFile').click();return;}
  const video=$('video'),canvas=document.createElement('canvas');canvas.width=video.videoWidth;canvas.height=video.videoHeight;canvas.getContext('2d').drawImage(video,0,0);
  try{await recognize(await canvasBlob(canvas,.95));}catch(error){message(describeError(error),true);}
};
$('samples').onchange=async()=>{
  const id=$('samples').value;if(!id||busy)return;
  try{const response=await fetch(`/api/samples/${encodeURIComponent(id)}/image`,{credentials:'same-origin'});if(!response.ok){const error=Error('Não foi possível abrir a foto de teste.');error.status=response.status;throw error;}await recognize(await response.blob());}
  catch(error){if(error.status===401)lockScreen();message(describeError(error),true);}
};
$('search').oninput=()=>{
  const query=$('search').value.trim().toLocaleLowerCase('pt-BR');$('catalogResults').replaceChildren();
  if(!query)return;
  const products=catalog.filter(item=>(item.name+' '+item.sku).toLocaleLowerCase('pt-BR').includes(query)).slice(0,20);
  for(const product of products)$('catalogResults').append(candidateButton(product));
  if(!products.length){const note=document.createElement('p');note.className='hint';note.textContent='Nenhum produto neste catálogo demonstrativo.';$('catalogResults').append(note);}
};
$('discard').onclick=()=>{pending=null;selected=null;$('result').hidden=true;controls(false);message('Foto descartada. Apresente outro produto.');};
$('confirm').onclick=async()=>{
  if(busy||!pending||!selected)return;
  prepareAudio();controls(true);
  try{
    const ack=await post(`/events/${pending}/confirm`,{session_id:session,sku:selected.sku});
    if(ack.status!=='acknowledged')throw Error('O simulador não confirmou a inclusão.');
    pending=null;beepAfterAck();
    await refreshReceipt();$('result').hidden=true;
    message('Uma unidade confirmada no cupom simulado. Apresente o próximo produto.');
  }catch(error){message(describeError(error),true);}
  finally{controls(false);}
};
$('done').onclick=async()=>{
  if(busy)return;controls(true);stopCamera();
  try{
    await post(`/sessions/${session}/close`);
    session=null;pending=null;selected=null;
    try{sessionStorage.removeItem('bixdata-demo-session');}catch{}
    $('result').hidden=true;await createSession();
    message('Demonstração finalizada, sem cobrança. Uma nova compra simulada está pronta.');
  }catch(error){message(describeError(error),true);}
  finally{controls(false);}
};
$('reconnect').onclick=()=>{ $('reconnect').hidden=true;loadApp(); };
window.addEventListener('pagehide',stopCamera);
window.addEventListener('offline',()=>{message('Celular sem conexão. Reconecte à internet para reconhecer.',true);$('connection').textContent='Sem conexão';});
window.addEventListener('online',()=>{message('Conexão restabelecida. Tente novamente.');});
(async()=>{
  try{const result=await call('/access');if(result.authenticated)await loadApp();else lockScreen();}
  catch(error){lockScreen();$('accessMessage').textContent=describeError(error);}
})();
