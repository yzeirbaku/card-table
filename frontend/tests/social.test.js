import test from 'node:test';
import assert from 'node:assert/strict';
import { canInvite, inviteAction, inviteRows, readLaunch, relationOf } from '../js/social.js';

const overview = {
  friends: [{ username: 'Sebi' }],
  incoming: [{ username: 'Arben' }],
  outgoing: [{ username: 'Lira' }],
};

test('relationOf names the four states, in any case', () => {
  assert.equal(relationOf(overview, 'sebi'), 'friends');
  assert.equal(relationOf(overview, 'LIRA'), 'sent');
  assert.equal(relationOf(overview, 'arben'), 'incoming');
  assert.equal(relationOf(overview, 'Nobody'), 'none');
});

const lobby = (players, seats = 4, status = 'lobby') => ({ room: { status, seats }, players });

test('canInvite: only a signed-in player at a lobby with a free seat', () => {
  const open = lobby([{ name: 'A' }]);
  assert.equal(canInvite(open, true), true);
  assert.equal(canInvite(open, false), false);
  assert.equal(canInvite(lobby([{ name: 'A' }], 4, 'playing'), true), false);
  assert.equal(canInvite(lobby([{}, {}, {}, {}]), true), false);
});

test('inviteRows marks friends already at the table, in any case, but not computers', () => {
  const friends = [{ username: 'Sebi' }, { username: 'Arben' }];
  const state = lobby([{ name: 'sebi' }, { name: 'Arben', computer: true }]);
  assert.deepEqual(inviteRows(friends, state), [
    { name: 'Sebi', here: true },
    { name: 'Arben', here: false },
  ]);
});

test('inviteAction decides what tapping an invite does', () => {
  assert.equal(inviteAction({ signedIn: false, currentCode: null, target: 'KQMX' }), 'signin');
  assert.equal(inviteAction({ signedIn: true, currentCode: null, target: 'KQMX' }), 'join');
  assert.equal(inviteAction({ signedIn: true, currentCode: 'KQMX', target: 'KQMX' }), 'stay');
  assert.equal(inviteAction({ signedIn: true, currentCode: 'ABCD', target: 'KQMX' }), 'ask');
});

test('readLaunch reads a join link, the friends link, and drops a bad code', () => {
  assert.deepEqual(readLaunch('?join=kqmx&from=Arben'), { join: 'KQMX', from: 'Arben', friends: false });
  assert.deepEqual(readLaunch('?join=kq7m&from=Arben'), { join: null, from: 'Arben', friends: false });
  assert.deepEqual(readLaunch('?friends'), { join: null, from: null, friends: true });
  assert.deepEqual(readLaunch('?join=12'), { join: null, from: null, friends: false });
  assert.deepEqual(readLaunch(''), { join: null, from: null, friends: false });
});
