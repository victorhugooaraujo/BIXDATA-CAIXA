import { createHash, createHmac, randomBytes, timingSafeEqual } from 'node:crypto';

const COOKIE = '__Host-bixdata_demo';
const SESSION_SECONDS = 8 * 60 * 60;
const MAX_BODY_BYTES = 2_000_000;
const UUID = '(?:[a-f0-9]{32}|[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})';
const ROUTES = [
  ['GET', /^\/api\/(?:health|catalog|samples)$/],
  ['POST', /^\/api\/sessions$/],
  ['GET', /^\/api\/sessions\/[a-f0-9]{32}\/receipt$/],
  ['POST', /^\/api\/sessions\/[a-f0-9]{32}\/close$/],
  ['POST', /^\/api\/events$/],
  ['POST', new RegExp(`^/api/events/${UUID}/confirm$`)],
  ['GET', /^\/api\/samples\/[a-zA-Z0-9_-]{1,128}\/image$/],
];

class BodyLimitError extends Error {}

function json(payload, status = 200, extraHeaders = {}) {
  return Response.json(payload, {
    status,
    headers: { 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', ...extraHeaders },
  });
}

function digest(value) {
  return createHash('sha256').update(value).digest();
}

function constantEqual(one, two) {
  return timingSafeEqual(digest(one), digest(two));
}

function configuration(env) {
  const { DEMO_ACCESS_CODE, SESSION_SECRET, BRIDGE_TOKEN, BACKEND_URL } = env;
  if (![DEMO_ACCESS_CODE, SESSION_SECRET, BRIDGE_TOKEN].every(value =>
    typeof value === 'string' && value.length >= 32)) return null;
  try {
    const url = new URL(BACKEND_URL);
    if (url.protocol !== 'https:' || !/^[a-z0-9-]+\.trycloudflare\.com$/.test(url.hostname)
      || url.username || url.password || url.port || url.pathname !== '/' || url.search || url.hash) return null;
    return { code: DEMO_ACCESS_CODE, secret: SESSION_SECRET, bridge: BRIDGE_TOKEN, backend: url.origin };
  } catch {
    return null;
  }
}

async function boundedBytes(body, limit) {
  if (!body) return new Uint8Array();
  const reader = body.getReader();
  const chunks = [];
  let length = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      length += value.byteLength;
      if (length > limit) {
        await reader.cancel();
        throw new BodyLimitError();
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  return Buffer.concat(chunks, length);
}

function signature(payload, secret) {
  return createHmac('sha256', secret).update(payload).digest('base64url');
}

function isAuthenticated(request, config, now) {
  const cookies = request.headers.get('cookie') || '';
  const value = cookies.split(';').map(item => item.trim()).find(item => item.startsWith(COOKIE + '='));
  if (!value) return false;
  const token = value.slice(COOKIE.length + 1);
  if (token.length > 512) return false;
  const [payload, mac, extra] = token.split('.');
  if (!payload || !mac || extra || !constantEqual(signature(payload, config.secret), mac)) return false;
  try {
    const session = JSON.parse(Buffer.from(payload, 'base64url').toString('utf8'));
    const current = Math.floor(now() / 1000);
    return session.version === 1 && Number.isSafeInteger(session.expires)
      && session.expires > current && session.expires <= current + SESSION_SECONDS
      && typeof session.nonce === 'string' && session.nonce.length === 32;
  } catch {
    return false;
  }
}

function cookie(value, maxAge = SESSION_SECONDS) {
  return `${COOKIE}=${value}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=${maxAge}`;
}

// Vercel preserves the browser pathname and injects both rewrite parameters.
// The observed pathname remains authoritative; query values must match it.
function resolveRoute(url) {
  if (url.hash) return null;
  if (!url.search) return url.pathname;
  const entries = [...url.searchParams.entries()];
  const routes = url.searchParams.getAll('__route');
  if (routes.length !== 1) return null;
  const route = routes[0];
  if (route.length > 300 || !/^[a-zA-Z0-9_-]+(?:\/[a-zA-Z0-9_-]+)*$/.test(route)) return null;
  // Also support direct invocation of the rewrite destination in local tests.
  if (url.pathname === '/api' && entries.length === 1) return '/api/' + route;
  const paths = url.searchParams.getAll('path');
  if (entries.length !== 2 || paths.length !== 1 || paths[0] !== route
    || url.pathname !== '/api/' + route) return null;
  return url.pathname;
}

/** A stateless proxy: the browser never receives the PC's bearer credential. */
export function createGateway(env, { fetchImpl = fetch, now = Date.now, timeoutMs = 60_000 } = {}) {
  const config = configuration(env);
  return async function gateway(request) {
    if (!config) return json({ detail: 'A demonstração está aguardando configuração do servidor.' }, 503);
    const url = new URL(request.url);
    const pathname = resolveRoute(url);
    if (!pathname) return json({ detail: 'Rota não disponível.' }, 404);
    const mutation = !['GET', 'HEAD', 'OPTIONS'].includes(request.method);
    if (mutation && request.headers.get('origin') !== url.origin) {
      return json({ detail: 'Origem não autorizada.' }, 403);
    }
    const authenticated = isAuthenticated(request, config, now);

    if (pathname === '/api/access') {
      if (request.method === 'GET') return json({ authenticated });
      if (request.method === 'DELETE') return json({ authenticated: false }, 200, { 'Set-Cookie': cookie('', 0) });
      if (request.method !== 'POST') return json({ detail: 'Método não disponível.' }, 405);
      if (!request.headers.get('content-type')?.startsWith('application/json')) {
        return json({ detail: 'Envie o código no formato JSON.' }, 415);
      }
      let body;
      try {
        const bytes = await boundedBytes(request.body, 4096);
        body = JSON.parse(Buffer.from(bytes).toString('utf8'));
      } catch (error) {
        return json({ detail: 'Código de acesso inválido.' }, error instanceof BodyLimitError ? 413 : 400);
      }
      if (typeof body?.code !== 'string' || !constantEqual(body.code, config.code)) {
        return json({ detail: 'Código de acesso inválido.' }, 401);
      }
      const payload = Buffer.from(JSON.stringify({
        version: 1, expires: Math.floor(now() / 1000) + SESSION_SECONDS,
        nonce: randomBytes(16).toString('hex'),
      })).toString('base64url');
      return json({ authenticated: true }, 200, {
        'Set-Cookie': cookie(payload + '.' + signature(payload, config.secret)),
      });
    }

    if (!authenticated) return json({ detail: 'Informe o código para acessar a demonstração.' }, 401);
    if (!ROUTES.some(([method, pattern]) => method === request.method && pattern.test(pathname))) {
      return json({ detail: 'Rota não disponível.' }, 404);
    }
    const headers = new Headers({ Authorization: 'Bearer ' + config.bridge });
    let body;
    if (request.method === 'POST') {
      const type = request.headers.get('content-type') || '';
      const expected = pathname === '/api/events' ? 'multipart/form-data;' : 'application/json';
      if (!type.startsWith(expected)) return json({ detail: 'Formato da requisição inválido.' }, 415);
      const declaredLength = Number(request.headers.get('content-length'));
      if (declaredLength > MAX_BODY_BYTES) return json({ detail: 'Reduza a foto para até 2 MB.' }, 413);
      try {
        body = await boundedBytes(request.body, MAX_BODY_BYTES);
      } catch (error) {
        return json({ detail: 'Reduza a foto para até 2 MB.' }, error instanceof BodyLimitError ? 413 : 400);
      }
      headers.set('Content-Type', type);
    }

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const upstream = await fetchImpl(config.backend + pathname, {
        method: request.method, headers, body, redirect: 'error', signal: controller.signal,
      });
      if (upstream.status === 401 || upstream.status === 403) {
        return json({ detail: 'A conexão com o PC precisa ser reconfigurada.' }, 502);
      }
      if (upstream.status >= 500) return json({ detail: 'O PC não está disponível. Confira se a ponte está ligada.' }, 503);
      if (upstream.status >= 300 && upstream.status < 400) return json({ detail: 'Resposta do servidor não autorizada.' }, 502);
      const bytes = await boundedBytes(upstream.body, 3_000_000);
      return new Response(bytes, {
        status: upstream.status,
        headers: {
          'Content-Type': upstream.headers.get('content-type') || 'application/json',
          'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
        },
      });
    } catch (error) {
      if (controller.signal.aborted || ['AbortError', 'TimeoutError'].includes(error?.name)) {
        return json({ detail: 'O reconhecimento demorou demais. Tente novamente com uma foto mais nítida.' }, 504);
      }
      if (error instanceof BodyLimitError) return json({ detail: 'Resposta do servidor acima do limite.' }, 502);
      return json({ detail: 'O PC não está disponível. Confira se a ponte está ligada.' }, 503);
    } finally {
      clearTimeout(timer);
    }
  };
}
