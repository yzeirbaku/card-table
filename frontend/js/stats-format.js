// How the profile page words its numbers. No DOM here, so it's tested on its own.

export const record = ({ won, lost }) => `${won}–${lost}`;

export function rate({ won, lost }) {
  const played = won + lost;
  return played ? `${Math.round((100 * won) / played)}%` : '–';
}

/** "51 wins · 21 losses · 71%": solo and teams together, under the name. */
export function tagLine(stats) {
  const won = stats.solo.total.won + stats.teams.total.won;
  const lost = stats.solo.total.lost + stats.teams.total.lost;
  if (!won && !lost) return 'No games yet';
  return `${won} ${won === 1 ? 'win' : 'wins'} · ${lost} ${lost === 1 ? 'loss' : 'losses'} · ${rate({ won, lost })}`;
}

export const initial = (name) => (name ? name.charAt(0).toUpperCase() : '?');

export function partnerLabel(partner) {
  if (partner.kind === 'user') return partner.name;
  return partner.kind === 'computer' ? 'a computer' : 'a guest';
}
