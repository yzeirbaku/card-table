// Spots for the other players around the table, in clockwise order starting on your left.
const SPOTS = { 1: [], 2: ['top'], 3: ['left', 'right'], 4: ['left', 'top', 'right'] };

/** Where everyone else sits, seen from `meId`. Players are in seat (join) order. */
export function seatPositions(players, meId) {
  const spots = SPOTS[players.length];
  if (!spots) throw new Error(`No table layout for ${players.length} players`);
  const me = players.findIndex((p) => p.id === meId);
  if (me < 0) return [];
  const others = [...players.slice(me + 1), ...players.slice(0, me)];
  return others.map((player, i) => ({ player, position: spots[i] }));
}
