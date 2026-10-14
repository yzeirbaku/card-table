// Cards moving on the table, drawn. The deal: card backs go out from the middle, one at a
// time, round the table, and your hand turns face up at the end. A play: the cards slide
// from the player to the pile. Only pictures: the server has already moved the cards.

import { div } from './dom.js';

const STEP_MS = 45; // between two cards leaving the deck
const FLIGHT_MS = 260;
const FAN = 5; // backs drawn per opponent (see table-view.js)

let run = 0; // bumped to stop a deal that is still going

export function stopDeal() {
  run++;
  const table = document.querySelector('.table');
  table.classList.remove('dealing');
  delete table.dataset.fan;
  document.querySelector('.deal-layer').replaceChildren();
}

/** Where `el`'s centre and size are in the table's own (unrotated) coordinates. */
function place(el, table) {
  const r = el.getBoundingClientRect();
  const t = table.getBoundingClientRect();
  if (document.getElementById('view-table').classList.contains('rotated')) {
    // the table is turned a quarter clockwise: its x runs down the screen, its y runs right to left
    return { x: r.top + r.height / 2 - t.top, y: t.right - (r.left + r.width / 2), w: r.height, h: r.width };
  }
  return { x: r.left + r.width / 2 - t.left, y: r.top + r.height / 2 - t.top, w: r.width, h: r.height };
}

const still = () => document.hidden || matchMedia('(prefers-reduced-motion: reduce)').matches;

/** Slide a play that just landed on the pile (`el`) in from where it came from (`fromEl`). */
export function flyIn(el, fromEl) {
  if (!fromEl || still()) return;
  const table = document.querySelector('.table');
  const from = place(fromEl, table);
  const to = place(el, table);
  el.animate(
    [{ translate: `${from.x - to.x}px ${from.y - to.y}px`, scale: 0.6 }, { translate: '0px 0px', scale: 1 }],
    { duration: 320, easing: 'cubic-bezier(.2, .7, .3, 1)' },
  );
}

const wait = (ms) => new Promise((resolve) => { setTimeout(resolve, ms); });

/**
 * Deal `perPlayer` cards to each of `positions` (the other seats, clockwise from your
 * left, e.g. ['left', 'top', 'right']) and to you, last in each turn round the table.
 */
export async function playDeal(positions, perPlayer) {
  stopDeal();
  if (still()) return;
  const mine = ++run;
  const table = document.querySelector('.table');
  const layer = document.querySelector('.deal-layer');
  table.classList.add('dealing');
  table.dataset.fan = '0';
  const from = place(document.querySelector('.play-area'), table);
  const deck = div('card-back deal-deck');
  deck.style.left = `${from.x}px`;
  deck.style.top = `${from.y}px`;
  layer.append(deck);

  const order = [...positions, 'me'];
  const total = perPlayer * order.length;
  for (let i = 0; i < total; i++) {
    if (run !== mine) return;
    const who = order[i % order.length];
    const k = Math.floor(i / order.length); // this player's k-th card
    const target = who === 'me'
      ? document.querySelectorAll('.hand .hand-card')[k]
      : document.querySelector(`.seat-${who} .backs`);
    if (target) fly(table, layer, from, place(target, table), who === 'me', mine);
    if (who === order.at(-1)) table.dataset.fan = String(Math.min(FAN, k + 1));
    await wait(STEP_MS);
  }
  await wait(FLIGHT_MS + 150);
  if (run !== mine) return;
  stopDeal();
  // Your cards turn face up. Animated on these elements only, so a re-render doesn't replay it.
  for (const card of document.querySelectorAll('.hand .hand-card')) {
    card.animate([{ transform: 'scaleX(0)' }, { transform: 'scaleX(1)' }], { duration: 320, easing: 'ease-out' });
  }
}

// A hidden tab barely runs timers: don't leave the hand hidden behind a deal crawling along.
document.addEventListener('visibilitychange', () => { if (document.hidden) stopDeal(); });

/** One back from the deck to `to`. Yours stay put face down until the deal is over. */
function fly(table, layer, from, to, keep, mine) {
  const card = div('card-back deal-card');
  card.style.left = `${from.x}px`;
  card.style.top = `${from.y}px`;
  layer.append(card);
  const turn = keep ? 0 : 90 + Math.round(Math.random() * 20 - 10);
  const scale = keep ? to.w / card.offsetWidth : 0.6;
  card.animate(
    [{ transform: 'translate(-50%, -50%)' },
     { transform: `translate(-50%, -50%) translate(${to.x - from.x}px, ${to.y - from.y}px) rotate(${turn}deg) scale(${scale})` }],
    { duration: FLIGHT_MS, easing: 'ease-out', fill: 'forwards' },
  ).finished.then(() => {
    if (run !== mine || !keep) card.remove();
  }, () => {});
}
