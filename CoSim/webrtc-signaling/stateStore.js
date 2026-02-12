const { randomUUID } = require('node:crypto');

const Redis = require('ioredis');

const DEFAULT_REDIS_URL = process.env.COSIM_REDIS_URL || 'redis://127.0.0.1:6379';
const DEFAULT_SERVER_ID = process.env.SIGNALING_SERVER_ID || randomUUID();

const ROOM_INDEX_KEY = 'signaling:rooms';

function clientKey(clientId) {
  return `signaling:clients:${clientId}`;
}

function roomMembersKey(roomId) {
  return `signaling:rooms:${roomId}:members`;
}

function serverKey(serverId) {
  return `signaling:servers:${serverId}`;
}

class StateStore {
  constructor(options = {}) {
    this.redis = options.redis || new Redis(options.redisUrl || DEFAULT_REDIS_URL);
    this.serverId = options.serverId || DEFAULT_SERVER_ID;
  }

  async registerClient({ id, roomId, role }) {
    if (!id || !roomId) {
      return;
    }
    const now = Date.now().toString();
    await this.redis
      .multi()
      .sadd(ROOM_INDEX_KEY, roomId)
      .sadd(roomMembersKey(roomId), id)
      .hset(clientKey(id), {
        id,
        roomId,
        role: role || '',
        serverId: this.serverId,
        updatedAt: now,
      })
      .exec();
  }

  async getClient(clientId) {
    if (!clientId) {
      return null;
    }
    const data = await this.redis.hgetall(clientKey(clientId));
    if (!data || !data.id) {
      return null;
    }
    return data;
  }

  async listParticipants(roomId) {
    if (!roomId) {
      return [];
    }
    const memberIds = await this.redis.smembers(roomMembersKey(roomId));
    if (!memberIds || memberIds.length === 0) {
      return [];
    }
    const pipeline = this.redis.pipeline();
    memberIds.forEach((id) => pipeline.hgetall(clientKey(id)));
    const responses = await pipeline.exec();
    const participants = [];
    for (const [, data] of responses) {
      if (data && data.id) {
        participants.push({ id: data.id, role: data.role || 'viewer' });
      }
    }
    return participants;
  }

  async removeClient({ id, roomId }) {
    if (!id) {
      return;
    }
    const multi = this.redis.multi();
    multi.del(clientKey(id));
    if (roomId) {
      multi.srem(roomMembersKey(roomId), id);
    }
    await multi.exec();

    if (roomId) {
      const remaining = await this.redis.scard(roomMembersKey(roomId));
      if (remaining === 0) {
        await this.redis.multi().del(roomMembersKey(roomId)).srem(ROOM_INDEX_KEY, roomId).exec();
      }
    }
  }

  async setHeartbeat(stats) {
    const payload = {
      serverId: this.serverId,
      connections: String(stats.connections || 0),
      rooms: String(stats.rooms || 0),
      updatedAt: Date.now().toString(),
    };
    await this.redis.hset(serverKey(this.serverId), payload);
    await this.redis.expire(serverKey(this.serverId), 30);
  }

  async cleanupServerState() {
    await this.redis.del(serverKey(this.serverId));
  }

  async close() {
    await this.redis.quit();
  }
}

module.exports = { StateStore, ROOM_INDEX_KEY, clientKey, roomMembersKey, serverKey };
