const Redis = require('ioredis');
const Y = require('yjs');

const DEFAULT_REDIS_URL = process.env.COSIM_REDIS_URL || 'redis://127.0.0.1:6379';
const DEFAULT_PREFIX = process.env.YJS_REDIS_PREFIX || 'collab:yjs:doc';

class RedisPersistence {
  constructor({ redisUrl = DEFAULT_REDIS_URL, redis = null, prefix = DEFAULT_PREFIX } = {}) {
    this.redis = redis || new Redis(redisUrl);
    this.externalRedis = Boolean(redis);
    this.prefix = prefix;
  }

  docKey(docName) {
    return `${this.prefix}:${docName}`;
  }

  async bindState(docName, ydoc) {
    await this._loadState(docName, ydoc);
    const listener = async () => {
      try {
        await this.writeState(docName, ydoc);
      } catch (error) {
        console.error('Failed to persist Yjs document', error);
      }
    };
    ydoc.on('update', listener);
  }

  async writeState(docName, ydoc) {
    const encoded = Buffer.from(Y.encodeStateAsUpdate(ydoc));
    await this.redis.set(this.docKey(docName), encoded.toString('base64'));
  }

  async _loadState(docName, ydoc) {
    const payload = await this.redis.get(this.docKey(docName));
    if (!payload) {
      return;
    }
    const update = Buffer.from(payload, 'base64');
    Y.applyUpdate(ydoc, new Uint8Array(update));
  }

  async destroy() {
    if (!this.externalRedis) {
      await this.redis.quit();
    }
  }
}

module.exports = { RedisPersistence };
