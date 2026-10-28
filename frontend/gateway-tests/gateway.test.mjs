import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFile } from 'node:fs/promises';
import { createGateway } from '../lib/gateway.mjs';

const env = {
  DEMO_ACCESS_CODE: 'a-long-demo-access-code-that-is-not-public',
  SESSION_SECRET: 's'.repeat(64),
  BRIDGE_TOKEN: 'b'.repeat(64),
  BACKEND_URL: 'https://example-demo.trycloudflare.com',
};
const origin = 'https://bixdata-demo.vercel.app';

function request(path, { method = 'GET', cookie, body, originHeader = origin, headers = {} } = {}) {
  const combined = new Headers(headers);
  if (cookie) combined.set('Cookie', cookie);
  if (method !== 'GET' && originHeader) combined.set('Origin', originHeader);
  return new Request(origin + path, { method, headers: combined, ...(body ? { body } : {}) });
}

async function login(gateway) {
  const response = await gateway(request('/api/access', {
    method: 'POST', body: JSON.stringify({ code: env.DEMO_ACCESS_CODE }),
    headers: { 'Content-Type': 'application/json' },
  }));
  assert.equal(response.status, 200);
  return response.headers.get('set-cookie').split(';')[0];
}

test('access requires the correct code and issues a secure non-readable eight-hour cookie', async () => {
  const gateway = createGateway(env);
  const denied = await gateway(request('/api/access', {
    method: 'POST', body: JSON.stringify({ code: 'wrong' }),
    headers: { 'Content-Type': 'application/json' },
  }));
  assert.equal(denied.status, 401);
  assert.equal(denied.headers.get('set-cookie'), null);
  const response = await gateway(request('/api/access', {
    method: 'POST', body: JSON.stringify({ code: env.DEMO_ACCESS_CODE }),
    headers: { 'Content-Type': 'application/json' },
  }));
  const header = response.headers.get('set-cookie');
  for (const flag of ['Secure', 'HttpOnly', 'SameSite=Strict', 'Path=/', 'Max-Age=28800']) {
    assert.ok(header.includes(flag));
  }
  assert.ok(!header.includes(env.DEMO_ACCESS_CODE));
  assert.ok(!header.includes(env.BRIDGE_TOKEN));
});

test('unauthenticated calls never reach the PC; access status does not reveal configuration', async () => {
  let calls = 0;
  const gateway = createGateway(env, { fetchImpl: async () => { calls++; return Response.json({}); } });
  assert.deepEqual(await (await gateway(request('/api/access'))).json(), { authenticated: false });
  assert.equal((await gateway(request('/api/catalog'))).status, 401);
  assert.equal(calls, 0);
});

test('authenticated requests receive only the scoped backend credential and a safe response', async () => {
  const gateway = createGateway(env, { fetchImpl: async (url, options) => {
    assert.equal(url, env.BACKEND_URL + '/api/health');
    assert.equal(options.headers.get('authorization'), 'Bearer ' + env.BRIDGE_TOKEN);
    assert.equal(options.headers.get('cookie'), null);
    assert.equal(options.headers.get('x-injected'), null);
    assert.equal(options.redirect, 'error');
    assert.ok(options.signal);
    return Response.json({ status: 'ready', simulated: true }, {
      headers: { 'set-cookie': 'backend-secret=yes', 'x-internal': 'hidden' },
    });
  } });
  const cookie = await login(gateway);
  const response = await gateway(request('/api/health', { cookie, headers: { 'x-injected': 'ignore' } }));
  assert.equal(response.status, 200);
  assert.equal(response.headers.get('set-cookie'), null);
  assert.equal(response.headers.get('x-internal'), null);
  assert.equal(response.headers.get('cache-control'), 'no-store');
  assert.equal((await response.json()).simulated, true);
});

test('cookie tampering and expiration fail; logout clears the browser cookie', async () => {
  let current = 100000;
  const gateway = createGateway(env, { now: () => current });
  const cookie = await login(gateway);
  assert.equal((await (await gateway(request('/api/access', { cookie }))).json()).authenticated, true);
  assert.equal((await gateway(request('/api/catalog', { cookie: cookie + 'x' }))).status, 401);
  current += 28801 * 1000;
  assert.equal((await gateway(request('/api/catalog', { cookie }))).status, 401);
  const logout = await gateway(request('/api/access', { method: 'DELETE', cookie }));
  assert.ok(logout.headers.get('set-cookie').includes('Max-Age=0'));
});

test('the real deadline aborts an unresponsive upstream request', async () => {
  let aborted = false;
  const gateway = createGateway(env, { timeoutMs: 10, fetchImpl: async (_url, options) =>
    new Promise((_resolve, reject) => options.signal.addEventListener('abort', () => {
      aborted = true;
      reject(new DOMException('aborted', 'AbortError'));
    }, { once: true })) });
  const cookie = await login(gateway);
  assert.equal((await gateway(request('/api/health', { cookie }))).status, 504);
  assert.equal(aborted, true);
});

test('cross-site and missing-origin mutations are rejected before authentication or proxying', async () => {
  const gateway = createGateway(env);
  const cookie = await login(gateway);
  for (const originHeader of ['https://evil.example', null]) {
    const response = await gateway(request('/api/sessions', {
      method: 'POST', cookie, originHeader, body: '{}',
      headers: { 'Content-Type': 'application/json' },
    }));
    assert.equal(response.status, 403);
  }
});

test('only declared route/method combinations are reachable and queries cannot select an upstream', async () => {
  let calls = 0;
  const gateway = createGateway(env, { fetchImpl: async () => { calls++; return Response.json({}); } });
  const cookie = await login(gateway);
  for (const path of ['/api/.env', '/api/docs', '/api/health?url=https://evil.example',
    '/api/samples/%2Fetc%2Fpasswd/image', '/api/events/not-a-uuid/confirm']) {
    assert.equal((await gateway(request(path, { cookie }))).status, 404, path);
  }
  assert.equal((await gateway(request('/api/catalog', { method: 'POST', cookie, body: '{}' }))).status, 404);
  assert.equal(calls, 0);
});

test('multipart uploads preserve bytes and content type but fail above two megabytes', async () => {
  let calls = 0;
  const boundary = 'boundary-demo';
  const raw = '--boundary-demo\r\nContent-Disposition: form-data; name="image"\r\n\r\nhello\r\n--boundary-demo--';
  const gateway = createGateway(env, { fetchImpl: async (url, options) => {
    calls++;
    assert.equal(url, env.BACKEND_URL + '/api/events');
    assert.equal(options.headers.get('content-type'), 'multipart/form-data; boundary=' + boundary);
    assert.equal(Buffer.from(options.body).toString(), raw);
    return Response.json({ decision: 'review' });
  } });
  const cookie = await login(gateway);
  const headers = { 'Content-Type': 'multipart/form-data; boundary=' + boundary };
  assert.equal((await gateway(request('/api/events', { method: 'POST', cookie, headers, body: raw }))).status, 200);
  assert.equal((await gateway(request('/api/events', { method: 'POST', cookie, headers, body: 'x'.repeat(2_000_001) }))).status, 413);
  assert.equal(calls, 1);
});

test('unsafe backend destinations and missing configuration fail closed', async () => {
  for (const BACKEND_URL of ['http://127.0.0.1:8765', 'https://evil.example',
    'https://example-demo.trycloudflare.com@evil.example',
    'https://example-demo.trycloudflare.com/arbitrary',
    'https://example-demo.trycloudflare.com?redirect=evil']) {
    const gateway = createGateway({ ...env, BACKEND_URL });
    assert.equal((await gateway(request('/api/access'))).status, 503);
  }
  assert.equal((await createGateway({})(request('/api/access'))).status, 503);
});

test('offline PC, timeout and upstream credential failures produce distinct safe errors', async () => {
  for (const [implementation, expected] of [
    [async () => { throw new TypeError('connection lost ' + env.BRIDGE_TOKEN); }, 503],
    [async () => { throw new DOMException('aborted', 'TimeoutError'); }, 504],
    [async () => new Response('invalid token', { status: 401 }), 502],
  ]) {
    const gateway = createGateway(env, { fetchImpl: implementation });
    const cookie = await login(gateway);
    const response = await gateway(request('/api/health', { cookie }));
    assert.equal(response.status, expected);
    const body = await response.text();
    assert.ok(!body.includes(env.BRIDGE_TOKEN));
    assert.ok(!body.includes('invalid token'));
  }
});

test('busy backend status and JSON errors survive without exposing upstream cookies', async () => {
  const gateway = createGateway(env, { fetchImpl: async () => Response.json(
    { detail: 'Reconhecimento ocupado; tente novamente.' }, { status: 429 },
  ) });
  const cookie = await login(gateway);
  const response = await gateway(request('/api/health', { cookie }));
  assert.equal(response.status, 429);
  assert.equal((await response.json()).detail, 'Reconhecimento ocupado; tente novamente.');
});

test('Vercel rewrite retains the selected API route in one explicit internal parameter', async () => {
  const config = JSON.parse(await readFile(new URL('../vercel.json', import.meta.url), 'utf8'));
  assert.deepEqual(config.rewrites, [{ source: '/api/:path*', destination: '/api?__route=:path*' }]);
});

test('rewritten access status and login retain browser origin and secure cookie policy', async () => {
  const gateway = createGateway(env);
  const status = await gateway(request('/api?__route=access'));
  assert.equal(status.status, 200);
  assert.deepEqual(await status.json(), { authenticated: false });
  const response = await gateway(request('/api?__route=access', {
    method: 'POST', body: JSON.stringify({ code: env.DEMO_ACCESS_CODE }),
    headers: { 'Content-Type': 'application/json' },
  }));
  assert.equal(response.status, 200);
  assert.ok(response.headers.get('set-cookie').includes('HttpOnly; Secure; SameSite=Strict'));
  const denied = await gateway(request('/api?__route=access', {
    method: 'POST', originHeader: 'https://evil.example', body: '{}',
    headers: { 'Content-Type': 'application/json' },
  }));
  assert.equal(denied.status, 403);
});

test('rewritten health and multipart events reach the exact allowed backend route', async () => {
  const requests = [];
  const gateway = createGateway(env, { fetchImpl: async (url, options) => {
    requests.push([url, options]);
    return Response.json({ simulated: true });
  } });
  const cookie = await login(gateway);
  assert.equal((await gateway(request('/api?__route=health', { cookie }))).status, 200);
  assert.equal(requests[0][0], env.BACKEND_URL + '/api/health');
  const payload = '--demo\r\nphoto\r\n--demo--';
  assert.equal((await gateway(request('/api?__route=events', {
    method: 'POST', cookie, body: payload,
    headers: { 'Content-Type': 'multipart/form-data; boundary=demo' },
  }))).status, 200);
  assert.equal(requests[1][0], env.BACKEND_URL + '/api/events');
  assert.equal(Buffer.from(requests[1][1].body).toString(), payload);
});

test('rewritten routes reject traversal, external schemas, duplicate and unrelated query parameters', async () => {
  let calls = 0;
  const gateway = createGateway(env, { fetchImpl: async () => { calls++; return Response.json({}); } });
  const cookie = await login(gateway);
  for (const path of [
    '/api?__route=health&url=https://evil.example',
    '/api?__route=health&__route=catalog',
    '/api?__route=', '/api?__route=events%2F..%2Fhealth',
    '/api?__route=https%3A%2F%2Fevil.example', '/api?__route=%2Fhealth',
    '/api?__route=events%255C..%255Chealth', '/api?__route=events//confirm',
    '/api/health?__route=catalog', '/api?url=health',
    '/api?__route=' + 'a'.repeat(301),
  ]) {
    assert.equal((await gateway(request(path, { cookie }))).status, 404, path);
  }
  assert.equal(calls, 0);
});

test('observed Vercel requests preserve original path plus matching route and path parameters', async () => {
  const requests = [];
  const gateway = createGateway(env, { fetchImpl: async (url, options) => {
    requests.push([url, options]);
    return Response.json({ simulated: true });
  } });
  const status = await gateway(request('/api/access?__route=access&path=access'));
  assert.equal(status.status, 200);
  assert.deepEqual(await status.json(), { authenticated: false });
  const response = await gateway(request('/api/access?__route=access&path=access', {
    method: 'POST', body: JSON.stringify({ code: env.DEMO_ACCESS_CODE }),
    headers: { 'Content-Type': 'application/json' },
  }));
  assert.equal(response.status, 200);
  const cookie = response.headers.get('set-cookie').split(';')[0];
  const health = await gateway(request('/api/health?path=health&__route=health', { cookie }));
  assert.equal(health.status, 200);
  assert.equal(requests[0][0], env.BACKEND_URL + '/api/health');
  const route = 'events/12345678-1234-1234-1234-123456789abc/confirm';
  const confirmation = await gateway(request(`/api/${route}?__route=${route}&path=${route}`, {
    method: 'POST', cookie, body: JSON.stringify({ session_id: 'a'.repeat(32), sku: 'demo-colgate' }),
    headers: { 'Content-Type': 'application/json' },
  }));
  assert.equal(confirmation.status, 200);
  assert.equal(requests[1][0], env.BACKEND_URL + '/api/' + route);
  const crossSite = await gateway(request('/api/access?__route=access&path=access', {
    method: 'POST', originHeader: 'https://evil.example', body: '{}',
    headers: { 'Content-Type': 'application/json' },
  }));
  assert.equal(crossSite.status, 403);
});

test('observed rewrite query can never override the original path or introduce arbitrary parameters', async () => {
  let calls = 0;
  const gateway = createGateway(env, { fetchImpl: async () => { calls++; return Response.json({}); } });
  const cookie = await login(gateway);
  for (const path of [
    '/api/health?__route=catalog&path=catalog',
    '/api/health?__route=health&path=catalog',
    '/api/health?__route=catalog&path=health',
    '/api/health?__route=health&path=health&extra=yes',
    '/api/health?__route=health&path=health&path=catalog',
    '/api/health?__route=health&__route=catalog&path=health',
    '/api/health?path=health',
    '/api/health?__route=https%3A%2F%2Fevil.example&path=health',
    '/api/health?__route=events%2F..%2Fhealth&path=health',
    '/api/unknown?__route=unknown&path=unknown',
  ]) {
    assert.equal((await gateway(request(path, { cookie }))).status, 404, path);
  }
  assert.equal(calls, 0);
});
