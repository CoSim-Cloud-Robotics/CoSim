const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const { once } = require('node:events');
const path = require('node:path');
const test = require('node:test');

const WebSocket = require('ws');
const Redis = require('ioredis');

const REDIS_URL = process.env.COSIM_REDIS_URL || process.env.REDIS_URL;
const SERVER_PATH = path.resolve(__dirname, '..', 'server.js');

const CONNECTION_TIMEOUT_MS = 3000;

async function canConnectRedis(url) {
  const client = new Redis(url, {
    lazyConnect: true,
    maxRetriesPerRequest: 1,
    connectTimeout: 500,
    retryStrategy: () => null,
  });
  try {
    await client.connect();
    await client.ping();
    return true;
  } catch (error) {
    return false;
  } finally {
    client.disconnect();
  }
}

function connectWebSocket(url) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(url);
    const timeout = setTimeout(() => {
      ws.terminate();
      reject(new Error(`Timed out connecting to ${url}`));
    }, CONNECTION_TIMEOUT_MS);
    ws.on('open', () => {
      clearTimeout(timeout);
      resolve(ws);
    });
    ws.on('error', (error) => {
      clearTimeout(timeout);
      reject(error);
    });
  });
}

function waitForMessage(ws, predicate, timeoutMs = 2000) {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      cleanup();
      reject(new Error('Timed out waiting for message'));
    }, timeoutMs);

    const onMessage = (data) => {
      let payload;
      try {
        payload = JSON.parse(data.toString());
      } catch (error) {
        return;
      }
      if (predicate(payload)) {
        cleanup();
        resolve(payload);
      }
    };

    const cleanup = () => {
      clearTimeout(timeout);
      ws.off('message', onMessage);
    };

    ws.on('message', onMessage);
  });
}

async function stopServer(proc) {
  if (!proc || proc.exitCode !== null) {
    return;
  }
  proc.kill('SIGTERM');
  const timeout = setTimeout(() => proc.kill('SIGKILL'), 2000);
  await once(proc, 'exit');
  clearTimeout(timeout);
}

test('relays offers across signaling servers', async (t) => {
  if (!REDIS_URL) {
    t.skip('COSIM_REDIS_URL not set');
    return;
  }
  if (!(await canConnectRedis(REDIS_URL))) {
    t.skip(`Redis not reachable at ${REDIS_URL}`);
    return;
  }

  const portA = 3105;
  const portB = 3107;
  const serverAId = `relay-a-${Date.now()}`;
  const serverBId = `relay-b-${Date.now()}`;

  const serverA = spawn('node', [SERVER_PATH], {
    env: {
      ...process.env,
      PORT: String(portA),
      COSIM_REDIS_URL: REDIS_URL,
      SIGNALING_SERVER_ID: serverAId,
    },
    stdio: 'ignore',
  });
  const serverB = spawn('node', [SERVER_PATH], {
    env: {
      ...process.env,
      PORT: String(portB),
      COSIM_REDIS_URL: REDIS_URL,
      SIGNALING_SERVER_ID: serverBId,
    },
    stdio: 'ignore',
  });

  t.after(async () => {
    await stopServer(serverA);
    await stopServer(serverB);
  });

  const wsA = await connectWebSocket(`ws://127.0.0.1:${portA}`);
  const wsB = await connectWebSocket(`ws://127.0.0.1:${portB}`);

  t.after(() => {
    wsA.close();
    wsB.close();
  });

  const welcomeA = await waitForMessage(wsA, (msg) => msg.type === 'welcome');
  const welcomeB = await waitForMessage(wsB, (msg) => msg.type === 'welcome');

  wsA.send(JSON.stringify({ type: 'join', roomId: 'relay-room', role: 'viewer' }));
  wsB.send(JSON.stringify({ type: 'join', roomId: 'relay-room', role: 'broadcaster' }));

  await waitForMessage(wsA, (msg) => msg.type === 'joined');
  await waitForMessage(wsB, (msg) => msg.type === 'joined');

  const offerPayload = { type: 'offer', sdp: 'v=0' };
  wsA.send(
    JSON.stringify({
      type: 'offer',
      targetId: welcomeB.clientId,
      offer: offerPayload,
    }),
  );

  const forwarded = await waitForMessage(
    wsB,
    (msg) => msg.type === 'offer' && msg.fromId === welcomeA.clientId,
  );
  assert.deepEqual(forwarded.offer, offerPayload);
});
