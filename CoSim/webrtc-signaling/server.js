/**
 * WebRTC Signaling Server for CoSim
 * 
 * Facilitates WebRTC peer connection establishment between browser clients
 * and simulation pods for low-latency video streaming.
 */

const WebSocket = require('ws');
const { v4: uuidv4 } = require('uuid');
const { setInterval } = require('node:timers');
const Redis = require('ioredis');

const { StateStore } = require('./stateStore');

const PORT = process.env.PORT || 3000;
const REDIS_URL = process.env.COSIM_REDIS_URL || 'redis://127.0.0.1:6379';
const RELAY_CHANNEL = 'signaling:relay';

// Store active connections and rooms
const rooms = new Map(); // roomId -> Set of clients
const clients = new Map(); // ws -> { id, roomId, role }
const stateStore = new StateStore();
const relayPublisher = new Redis(REDIS_URL);
const relaySubscriber = new Redis(REDIS_URL);
const HEARTBEAT_MS = Number(process.env.SIGNALING_HEARTBEAT_MS || 5000);
const heartbeatTimer = setInterval(() => {
  stateStore
    .setHeartbeat({ connections: clients.size, rooms: rooms.size })
    .catch((err) => {
      console.error('Failed to publish heartbeat', err);
    });
}, HEARTBEAT_MS);
heartbeatTimer.unref();

relaySubscriber.subscribe(RELAY_CHANNEL, (err) => {
  if (err) {
    console.error('Failed to subscribe to relay channel', err);
  }
});

relaySubscriber.on('message', async (_, raw) => {
  try {
    const payload = JSON.parse(raw);
    await handleRelayDelivery(payload);
  } catch (error) {
    console.error('Failed to process relay payload', error);
  }
});

// Create WebSocket server
const wss = new WebSocket.Server({ port: PORT });

console.log(`🚀 WebRTC Signaling Server started on port ${PORT}`);

wss.on('connection', (ws) => {
  const clientId = uuidv4();
  
  console.log(`✅ Client connected: ${clientId}`);
  
  // Initialize client metadata
  clients.set(ws, {
    id: clientId,
    roomId: null,
    role: null, // 'viewer' or 'broadcaster'
  });
  
  // Send welcome message with client ID
  send(ws, {
    type: 'welcome',
    clientId: clientId,
  });
  
  ws.on('message', async (data) => {
    try {
      const message = JSON.parse(data);
      await handleMessage(ws, message);
    } catch (error) {
      console.error(`❌ Failed to parse message: ${error.message}`);
      send(ws, {
        type: 'error',
        error: 'Invalid JSON message',
      });
    }
  });
  
  ws.on('close', () => {
    handleDisconnect(ws).catch((err) => {
      console.error('Failed to handle disconnect', err);
    });
  });
  
  ws.on('error', (error) => {
    console.error(`❌ WebSocket error for ${clientId}:`, error.message);
  });
});

/**
 * Handle incoming messages from clients
 */
async function handleMessage(ws, message) {
  const client = clients.get(ws);
  
  console.log(`📨 Message from ${client.id}: ${message.type}`);
  
  switch (message.type) {
    case 'join':
      await handleJoin(ws, message);
      break;
      
    case 'offer':
      await handleOffer(ws, message);
      break;
      
    case 'answer':
      await handleAnswer(ws, message);
      break;
      
    case 'ice-candidate':
      await handleIceCandidate(ws, message);
      break;
      
    case 'leave':
      await handleLeave(ws);
      break;
      
    default:
      console.warn(`⚠️  Unknown message type: ${message.type}`);
      send(ws, {
        type: 'error',
        error: `Unknown message type: ${message.type}`,
      });
  }
}

/**
 * Handle client joining a room
 */
async function handleJoin(ws, message) {
  const client = clients.get(ws);
  const { roomId, role } = message;
  
  if (!roomId || !role) {
    send(ws, {
      type: 'error',
      error: 'roomId and role are required',
    });
    return;
  }
  
  // Leave current room if any
  if (client.roomId) {
    await handleLeave(ws);
  }
  
  // Join new room
  client.roomId = roomId;
  client.role = role;
  
  if (!rooms.has(roomId)) {
    rooms.set(roomId, new Set());
  }
  
  rooms.get(roomId).add(ws);
  
  await stateStore.registerClient({ id: client.id, roomId, role });

  console.log(`👥 Client ${client.id} joined room ${roomId} as ${role}`);
  
  // Notify client
  const participants = await stateStore.listParticipants(roomId);
  send(ws, {
    type: 'joined',
    roomId: roomId,
    role: role,
    participants,
  });
  
  // Notify other participants
  broadcast(ws, roomId, {
    type: 'peer-joined',
    peerId: client.id,
    role: role,
  });
}

/**
 * Handle WebRTC offer
 */
async function handleOffer(ws, message) {
  const client = clients.get(ws);
  const { targetId, offer } = message;
  
  if (!targetId || !offer) {
    send(ws, {
      type: 'error',
      error: 'targetId and offer are required',
    });
    return;
  }
  
  const forwarded = await relayOrSend(
    ws,
    targetId,
    {
      type: 'offer',
      fromId: client.id,
      offer: offer,
    },
    { notifyMissing: true },
  );

  if (forwarded) {
    console.log(`🔄 Forwarded offer from ${client.id} to ${targetId}`);
  }
}

/**
 * Handle WebRTC answer
 */
async function handleAnswer(ws, message) {
  const client = clients.get(ws);
  const { targetId, answer } = message;
  
  if (!targetId || !answer) {
    send(ws, {
      type: 'error',
      error: 'targetId and answer are required',
    });
    return;
  }
  
  const forwarded = await relayOrSend(
    ws,
    targetId,
    {
      type: 'answer',
      fromId: client.id,
      answer: answer,
    },
    { notifyMissing: true },
  );

  if (forwarded) {
    console.log(`🔄 Forwarded answer from ${client.id} to ${targetId}`);
  }
}

/**
 * Handle ICE candidate
 */
async function handleIceCandidate(ws, message) {
  const client = clients.get(ws);
  const { targetId, candidate } = message;
  
  if (!targetId || !candidate) {
    send(ws, {
      type: 'error',
      error: 'targetId and candidate are required',
    });
    return;
  }
  
  const forwarded = await relayOrSend(
    ws,
    targetId,
    {
      type: 'ice-candidate',
      fromId: client.id,
      candidate: candidate,
    },
    { notifyMissing: false },
  );

  if (forwarded) {
    console.log(`🧊 Forwarded ICE candidate from ${client.id} to ${targetId}`);
  }
}

/**
 * Handle client leaving a room
 */
async function handleLeave(ws) {
  const client = clients.get(ws);
  
  if (!client.roomId) {
    return;
  }
  
  const roomId = client.roomId;
  const room = rooms.get(roomId);
  
  if (room) {
    room.delete(ws);
    
    // Notify others in room
    broadcast(ws, roomId, {
      type: 'peer-left',
      peerId: client.id,
    });
    
    // Clean up empty rooms
    if (room.size === 0) {
      rooms.delete(roomId);
      console.log(`🗑️  Removed empty room ${roomId}`);
    }
  }
  
  await stateStore.removeClient({ id: client.id, roomId });

  console.log(`👋 Client ${client.id} left room ${roomId}`);
  
  client.roomId = null;
  client.role = null;
}

/**
 * Handle client disconnect
 */
async function handleDisconnect(ws) {
  const client = clients.get(ws);
  
  if (!client) {
    return;
  }
  
  console.log(`❌ Client disconnected: ${client.id}`);
  
  // Leave room if joined
  await handleLeave(ws);
  
  // Remove from clients map
  clients.delete(ws);
}

/**
 * Send message to a specific client
 */
function send(ws, message) {
  if (ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(message));
  }
}

/**
 * Broadcast message to all clients in a room except sender
 */
function broadcast(sender, roomId, message) {
  const room = rooms.get(roomId);
  
  if (!room) {
    return;
  }
  
  room.forEach((ws) => {
    if (ws !== sender) {
      send(ws, message);
    }
  });
}

/**
 * Find client WebSocket by ID
 */
function findClientById(clientId) {
  for (const [ws, client] of clients.entries()) {
    if (client.id === clientId) {
      return ws;
    }
  }
  return null;
}

async function relayOrSend(ws, targetId, message, options = {}) {
  const notifyMissing = options.notifyMissing !== undefined ? options.notifyMissing : true;
  const targetWs = findClientById(targetId);
  if (targetWs) {
    send(targetWs, message);
    return true;
  }

  const remoteClient = await stateStore.getClient(targetId);
  if (!remoteClient || !remoteClient.serverId) {
    if (notifyMissing) {
      send(ws, {
        type: 'error',
        error: `Target client ${targetId} not found`,
      });
    }
    return false;
  }

  await relayPublisher.publish(
    RELAY_CHANNEL,
    JSON.stringify({
      originServerId: stateStore.serverId,
      targetServerId: remoteClient.serverId,
      targetId,
      message,
    }),
  );
  return true;
}

async function handleRelayDelivery(payload) {
  if (!payload || payload.targetServerId !== stateStore.serverId) {
    return;
  }
  if (payload.originServerId === stateStore.serverId) {
    return;
  }
  const targetWs = findClientById(payload.targetId);
  if (!targetWs || !payload.message) {
    return;
  }
  send(targetWs, payload.message);
}

// Health check endpoint (for Docker)
const http = require('http');
const healthServer = http.createServer((req, res) => {
  if (req.url === '/health') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({
      status: 'healthy',
      connections: clients.size,
      rooms: rooms.size,
    }));
  } else {
    res.writeHead(404);
    res.end();
  }
});

healthServer.listen(PORT + 1, () => {
  console.log(`❤️  Health check server on port ${PORT + 1}`);
});

// Graceful shutdown
process.on('SIGTERM', () => {
  console.log('📴 SIGTERM received, closing server...');
  clearInterval(heartbeatTimer);
  Promise.allSettled([
    stateStore.cleanupServerState(),
    stateStore.close(),
    relayPublisher.quit(),
    relaySubscriber.quit(),
  ])
    .catch(() => {})
    .finally(() => {
      wss.close(() => {
        healthServer.close(() => {
          console.log('👋 Server shut down gracefully');
          process.exit(0);
        });
      });
    });
});
