const Redis = require('ioredis');
const awarenessProtocol = require('y-protocols/dist/awareness.cjs');

const DEFAULT_REDIS_URL = process.env.COSIM_REDIS_URL || 'redis://127.0.0.1:6379';
const CHANNEL_PREFIX = process.env.YJS_AWARENESS_CHANNEL_PREFIX || 'collab:yjs:awareness';

class RedisAwareness {
  constructor({ redisUrl = DEFAULT_REDIS_URL, publisher = null, subscriber = null } = {}) {
    this.publisher = publisher || new Redis(redisUrl);
    this.subscriber = subscriber || new Redis(redisUrl);
    this.externalPublisher = Boolean(publisher);
    this.externalSubscriber = Boolean(subscriber);
    this.prefix = CHANNEL_PREFIX;
    this.boundDocs = new Map();
    this.origin = Symbol('redis-awareness');

    this.subscriber.on('message', (channel, payload) => {
      this.handleMessage(channel, payload);
    });
  }

  channelName(docName) {
    return `${this.prefix}:${docName}`;
  }

  async watch(docName, awareness) {
    if (!docName || !awareness || this.boundDocs.has(docName)) {
      return;
    }
    const handler = ({ added, updated, removed }, origin) => {
      if (origin === this.origin) {
        return;
      }
      const changed = added.concat(updated, removed);
      if (changed.length === 0) {
        return;
      }
      const update = awarenessProtocol.encodeAwarenessUpdate(awareness, changed);
      this.publisher.publish(this.channelName(docName), Buffer.from(update).toString('base64')).catch((err) => {
        console.error('Failed to publish awareness update', err);
      });
    };

    awareness.on('update', handler);
    this.boundDocs.set(docName, { awareness, handler });
    await this.subscriber.subscribe(this.channelName(docName));
  }

  handleMessage(channel, payload) {
    if (!channel.startsWith(this.prefix)) {
      return;
    }
    const docName = channel.slice(this.prefix.length + 1);
    const entry = this.boundDocs.get(docName);
    if (!entry || !payload) {
      return;
    }
    try {
      const update = Buffer.from(payload, 'base64');
      awarenessProtocol.applyAwarenessUpdate(entry.awareness, new Uint8Array(update), this.origin);
    } catch (error) {
      console.error('Failed to apply awareness update', error);
    }
  }

  async destroy() {
    for (const { awareness, handler } of this.boundDocs.values()) {
      awareness.off('update', handler);
    }
    this.boundDocs.clear();
    const tasks = [];
    if (!this.externalSubscriber) {
      tasks.push(this.subscriber.quit());
    }
    if (!this.externalPublisher) {
      tasks.push(this.publisher.quit());
    }
    await Promise.allSettled(tasks);
  }
}

module.exports = { RedisAwareness };
