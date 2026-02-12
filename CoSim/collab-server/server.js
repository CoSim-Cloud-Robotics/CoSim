#!/usr/bin/env node

/**
 * CoSim Yjs Collaboration Server
 * Provides real-time CRDT synchronization for multi-user editing
 */

const WebSocket = require('ws');
const http = require('http');
const { setupWSConnection, docs, setPersistence } = require('y-websocket/bin/utils');

const { RedisPersistence } = require('./redisPersistence');
const { RedisAwareness } = require('./redisAwareness');

const PORT = process.env.PORT || 1234;
const PERSISTENCE_DIR = process.env.PERSISTENCE_DIR || '/data';
const REDIS_URL = process.env.COSIM_REDIS_URL || 'redis://127.0.0.1:6379';

console.log(`Starting CoSim Yjs Collaboration Server on port ${PORT}`);
console.log(`Persistence directory: ${PERSISTENCE_DIR}`);
console.log(`Redis URL: ${REDIS_URL}`);

const redisPersistence = new RedisPersistence({ redisUrl: REDIS_URL });
setPersistence(redisPersistence);
const awarenessBridge = new RedisAwareness({ redisUrl: REDIS_URL });

const server = http.createServer((req, res) => {
  if (req.url === '/health') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ status: 'healthy', uptime: process.uptime() }));
    return;
  }
  res.writeHead(200, { 'Content-Type': 'text/html' });
  res.end('CoSim Yjs Collaboration Server Running');
});

const wss = new WebSocket.Server({ server });

wss.on('connection', (ws, req) => {
  const docName = req.url.slice(1).split('?')[0] || 'default';
  console.log(`New connection for document: ${docName}`);
  
  setupWSConnection(ws, req, {
    gc: true,
    docName,
  });

  const doc = docs.get(docName);
  if (doc) {
    awarenessBridge.watch(docName, doc.awareness).catch((error) => {
      console.error('Failed to bind Redis awareness', error);
    });
  }
});

wss.on('error', (error) => {
  console.error('WebSocket server error:', error);
});

server.listen(PORT, '0.0.0.0', () => {
  console.log(`✓ Yjs collaboration server listening on ws://0.0.0.0:${PORT}`);
  console.log(`✓ Health check available at http://0.0.0.0:${PORT}/health`);
});

// Graceful shutdown
const shutdown = (signal) => {
  console.log(`${signal} received, closing server...`);
  Promise.allSettled([awarenessBridge.destroy(), redisPersistence.destroy()]).finally(() => {
    wss.close(() => {
      server.close(() => {
        console.log('Server closed');
        process.exit(0);
      });
    });
  });
};

process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('SIGINT', () => shutdown('SIGINT'));
