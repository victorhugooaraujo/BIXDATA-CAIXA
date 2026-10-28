export function fitDimensions(width,height,max=1600){
  if(!Number.isFinite(width)||!Number.isFinite(height)||width<=0||height<=0)throw Error('Imagem com dimensões inválidas.');
  const scale=Math.min(1,max/Math.max(width,height));
  return {width:Math.max(1,Math.round(width*scale)),height:Math.max(1,Math.round(height*scale))};
}
export function selectedProduct(sku,catalog){return catalog.find(item=>item.sku===sku)||null;}
export function resolveSelection(sku,catalog,{busy=false,automatic=false}={}){
  if(busy&&!automatic)return undefined;
  return selectedProduct(sku,catalog);
}
export function receiptSummary(receipt){
  const lines=receipt.lines;
  if(!Array.isArray(lines)||lines.some(line=>!Number.isSafeInteger(line.price_cents)||line.price_cents<0))throw Error('Resposta inválida do cupom.');
  const identifiers=lines.map(line=>line.event_id);
  if(identifiers.some(id=>typeof id!=='string'||!id)||new Set(identifiers).size!==identifiers.length)throw Error('Evento ausente ou duplicado no cupom.');
  const total=lines.reduce((sum,item)=>sum+item.price_cents,0);
  if(total!==receipt.total_cents)throw Error('Valores inconsistentes no cupom.');
  return {lines,count:lines.length,total};
}
export function describeError(error){
  if(error.status===401)return 'Acesso expirado. Digite novamente o código da demonstração.';
  if(error.status===429)return 'Reconhecimento ocupado. Aguarde alguns segundos e tente novamente.';
  if([502,503,504].includes(error.status))return 'O PC de processamento está indisponível. Mantenha o servidor ligado e tente novamente.';
  if(error.status===413)return 'Foto acima do limite de envio. Tente outra foto com menor resolução.';
  if(error.name==='AbortError'||error.name==='TimeoutError')return 'O reconhecimento excedeu o tempo de espera. Tente novamente.';
  if(error instanceof TypeError)return 'Sem conexão. Confira a internet e tente novamente.';
  return error.message||'Não foi possível concluir. Tente novamente.';
}
export async function requestJson(url,options={},transport=fetch){
  let response;
  try{response=await transport(url,{...options,credentials:'same-origin',cache:'no-store'});}catch(error){throw error;}
  let value;
  try{value=await response.json();}catch{value=null;}
  if(!response.ok){const error=Error(value?.detail||value?.error||describeError({status:response.status}));error.status=response.status;throw error;}
  if(value===null)throw Error('Resposta inválida do servidor.');
  return value;
}
