import { cleanCode, isCompleteCode } from './code.js';

const same = (a, b) => a.toLowerCase() === b.toLowerCase();

/** How `name` stands with you, from an overview { friends, incoming, outgoing } of plain usernames. */
export function relationOf(overview, name) {
  const has = (list) => list.some((entry) => same(entry, name));
  if (has(overview.friends)) return 'friends';
  if (has(overview.outgoing)) return 'sent';
  if (has(overview.incoming)) return 'incoming';
  return 'none';
}

/** The invite button shows for a signed-in player at a lobby with room left. */
export function canInvite(state, signedIn) {
  return signedIn && state.room.status === 'lobby' && state.players.length < state.room.seats;
}

/** One row per friend; `here` when a person (not a computer) of that name is at the table. */
export function inviteRows(friends, state) {
  const people = state.players.filter((p) => !p.computer);
  return friends.map((name) => ({ name, here: people.some((p) => same(p.name, name)) }));
}

/** What tapping an invite does: sign in first, nothing (already there), join, or ask before leaving a table. */
export function inviteAction({ signedIn, currentCode, target }) {
  if (!signedIn) return 'signin';
  if (!currentCode) return 'join';
  return currentCode === target ? 'stay' : 'ask';
}

/** What the page was opened for: ?join=CODE&from=Name (a bad code is dropped) or ?friends. */
export function readLaunch(search) {
  const params = new URLSearchParams(search);
  const code = cleanCode(params.get('join') ?? '');
  return {
    join: isCompleteCode(code) ? code : null,
    from: params.get('from'),
    friends: params.has('friends'),
  };
}

/** The question before leaving one table for an invite. `playing`: a game is on where you are now. */
export function joinQuestion({ from, playing, game }) {
  return {
    title: from ? `Join ${from}'s table?` : 'Join the other table?',
    text: playing ? `You're in a game of ${game}. Leaving ends it for everyone at this table.` : "You'll leave the table you're at.",
    stay: 'Stay',
    go: 'Leave and join',
  };
}
