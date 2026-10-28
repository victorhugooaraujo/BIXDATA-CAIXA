import test from 'node:test';
import assert from 'node:assert/strict';
import {fitDimensions, selectedProduct, resolveSelection, receiptSummary, requestJson, describeError} from '../public/mobile-core.mjs';

test('phone portrait photos retain orientation and never exceed upload dimensions', () => {
  assert.deepEqual(fitDimensions(3024,4032), {width:1200,height:1600});
  assert.deepEqual(fitDimensions(400,300), {width:400,height:300});
  assert.throws(()=>fitDimensions(0,20), /dimens/);
});
test('model candidate is selected only when present in actual catalog', () => {
  const catalog=[{sku:'one',name:'One',price_cents:100}];
  assert.equal(selectedProduct('one',catalog).sku,'one');
  assert.equal(selectedProduct('invented',catalog),null);
  assert.equal(selectedProduct(null,catalog),null);
});
test('model selection is prepared while busy but user changes cannot race an upload',()=>{
  const catalog=[{sku:'a',name:'A'}];
  assert.equal(resolveSelection('a',catalog,{busy:true}),undefined);
  assert.equal(resolveSelection('a',catalog,{busy:true,automatic:true}).sku,'a');
  assert.equal(resolveSelection('missing',catalog,{busy:true,automatic:true}),null);
});
test('receipt totals use acknowledged lines, preserving two equal physical items', () => {
  const result=receiptSummary({lines:[{event_id:'1',sku:'a',price_cents:100},{event_id:'2',sku:'a',price_cents:100}],total_cents:200});
  assert.equal(result.count,2);
  assert.equal(result.total,200);
  assert.throws(()=>receiptSummary({lines:[{price_cents:100}],total_cents:999}),/cupom/);
  assert.throws(()=>receiptSummary({lines:[{event_id:'same',price_cents:100},{event_id:'same',price_cents:100}],total_cents:200}),/duplicad/);
});
test('an upstream HTML error is converted to a useful error, never a JSON parse leak', async () => {
  await assert.rejects(requestJson('/api/events',{},async()=>new Response('<html>down</html>',{status:503})), error=>error.status===503 && /PC|servidor/i.test(error.message));
});
test('expired access remains distinguishable from invalid item confirmation', async () => {
  await assert.rejects(requestJson('/api/catalog',{},async()=>new Response('{"detail":"expired"}',{status:401})),error=>error.status===401);
  await assert.rejects(requestJson('/api/events/a/confirm',{},async()=>new Response('{"detail":"Evento expirado"}',{status:409})),error=>error.status===409 && /expirado/.test(error.message));
});
test('only acknowledged API responses yield data; timeout and busy messages are actionable',async()=>{
  assert.deepEqual(await requestJson('/api/health',{},async()=>Response.json({simulated:true})),{simulated:true});
  assert.match(describeError({status:429}),/ocupado/i);
  assert.match(describeError({name:'AbortError'}),/tempo/i);
});
