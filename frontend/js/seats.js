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

/** The lobby's spot for each seat (by index) of a `seats`-seat table: yours at the bottom (seat 0's
 *  until you sit), the rest clockwise from your left, as they will be at the table. */
export function lobbySpots(seats, mySeat) {
  const spots = SPOTS[seats];
  if (!spots) throw new Error(`No table layout for ${seats} players`);
  const me = mySeat ?? 0;
  return Array.from({ length: seats }, (_, seat) => (seat === me ? 'bottom' : spots[(seat - me + seats) % seats - 1]));
}
