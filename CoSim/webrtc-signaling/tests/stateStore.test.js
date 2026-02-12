const test = require('node:test');
const assert = require('node:assert/strict');

const RedisMock = require('ioredis-mock');

const { StateStore, ROOM_INDEX_KEY, roomMembersKey, clientKey } = require('../stateStore');

test('registers participants and lists them', async () => {
  const redis = new RedisMock();
  const store = new StateStore({ redis, serverId: 'test-server' });

  await store.registerClient({ id: 'client-1', roomId: 'room-1', role: 'viewer' });
  await store.registerClient({ id: 'client-2', roomId: 'room-1', role: 'broadcaster' });

  const participants = await store.listParticipants('room-1');
  assert.equal(participants.length, 2);
  const roles = participants.reduce((acc, p) => ({ ...acc, [p.id]: p.role }), {});
  assert.equal(roles['client-1'], 'viewer');
  assert.equal(roles['client-2'], 'broadcaster');

  await store.close();
});

test('removes participants and cleans up empty rooms', async () => {
  const redis = new RedisMock();
  const store = new StateStore({ redis, serverId: 'test' });

  await store.registerClient({ id: 'client-1', roomId: 'room-xyz', role: 'viewer' });
  await store.removeClient({ id: 'client-1', roomId: 'room-xyz' });

  const members = await redis.smembers(roomMembersKey('room-xyz'));
  assert.equal(members.length, 0);

  const rooms = await redis.smembers(ROOM_INDEX_KEY);
  assert.deepEqual(rooms, []);

  const clientEntry = await redis.hgetall(clientKey('client-1'));
  assert.deepEqual(clientEntry, {});

  await store.close();
});

test('getClient returns stored metadata', async () => {
  const redis = new RedisMock();
  const store = new StateStore({ redis, serverId: 'server-a' });

  await store.registerClient({ id: 'client-42', roomId: 'room-42', role: 'viewer' });

  const entry = await store.getClient('client-42');
  assert.equal(entry.id, 'client-42');
  assert.equal(entry.roomId, 'room-42');
  assert.equal(entry.role, 'viewer');
  assert.equal(entry.serverId, 'server-a');

  await store.close();
});
