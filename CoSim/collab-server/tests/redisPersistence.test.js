const test = require('node:test');
const assert = require('node:assert/strict');

const Redis = require('ioredis-mock');
const Y = require('yjs');

const { RedisPersistence } = require('../redisPersistence');

function decodeDoc(buffer) {
  const doc = new Y.Doc();
  Y.applyUpdate(doc, new Uint8Array(buffer));
  return doc;
}

test('redis persistence loads and saves document state', async () => {
  const redis = new Redis();
  const persistence = new RedisPersistence({ redis, prefix: 'test:yjs' });
  const docName = 'doc-123';

  // Seed redis with an encoded document
  const seedDoc = new Y.Doc();
  seedDoc.getText('content').insert(0, 'hello');
  const seedUpdate = Buffer.from(Y.encodeStateAsUpdate(seedDoc));
  await redis.set(`${persistence.prefix}:${docName}`, seedUpdate.toString('base64'));

  const doc = new Y.Doc();
  doc.getText('content');
  await persistence.bindState(docName, doc);
  assert.equal(doc.getText('content').toString(), 'hello');

  doc.getText('content').insert(5, ' world');
  await persistence.writeState(docName, doc);

  const stored = await redis.get(`${persistence.prefix}:${docName}`);
  const decoded = decodeDoc(Buffer.from(stored, 'base64'));
  assert.equal(decoded.getText('content').toString(), 'hello world');

  await persistence.destroy();
});
