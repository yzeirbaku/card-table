import { seatPositions } from './seats.js';

const MAX_BACKS = 7; // card backs drawn per opponent; the count shows the real number

export function initTable({ onLeave }) {
  const menu = document.getElementById('table-menu');
  document.getElementById('btn-table-menu').addEventListener('click', () => { menu.hidden = !menu.hidden; });
  document.getElementById('btn-table-leave').addEventListener('click', () => {
    menu.hidden = true;
    onLeave();
  });
}

export function renderTable(state, meId) {
  const me = state.players.find((p) => p.id === meId);
  document.querySelector('.seat-me').replaceChildren(...(me ? [plate(me)] : []));
  document.querySelector('.seats').replaceChildren(
    ...seatPositions(state.players, meId).map(({ player, position }) => seat(player, position)),
  );
}

function seat(player, position) {
  const el = div(`seat seat-${position}`);
  const backs = div('backs');
  for (let i = 0; i < Math.min(player.hand_count, MAX_BACKS); i++) backs.append(div('card-back'));
  el.append(backs, plate(player));
  return el;
}

function plate(player) {
  const el = div(player.connected ? 'plate' : 'plate offline');
  const name = document.createElement('span');
  name.textContent = player.name;
  el.append(div('dot'), name);
  const count = document.createElement('span');
  count.className = 'count';
  count.textContent = String(player.hand_count);
  el.append(count);
  return el;
}

function div(className) {
  const el = document.createElement('div');
  el.className = className;
  return el;
}
