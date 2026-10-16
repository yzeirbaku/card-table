// Dragging cards from your hand onto the pile: the other way to play them (pick and press Play is
// the first). Only pictures and a message: the server still says whether the play is allowed.

const THRESHOLD = 10; // px a press moves before it's a drag and not a tap
const SWALLOW_MS = 400; // the click a drag ends with isn't a tap on the card

/** A press that moved this far is a drag. */
export function isDrag(dx, dy) {
  return Math.hypot(dx, dy) > THRESHOLD;
}

/** A move on the screen in the table's own coordinates (turned a quarter clockwise on a portrait phone). */
export function tableDelta(dx, dy, rotated) {
  return rotated ? { x: dy, y: -dx } : { x: dx, y: dy };
}

export function inside(rect, x, y) {
  return x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom;
}

/**
 * The cards that go with a drag of `code`, or null when it can't be dragged. Your picks come along
 * (the card joins them if it wasn't picked); giving in the swap, it's just that card, if it's one you may give.
 */
export function dragGroup(selected, code, choices) {
  if (choices.length) return choices.includes(code) ? [code] : null;
  return selected.includes(code) ? selected : [...selected, code];
}

let press = null; // { id, code, x, y, cards } a press on a card in your hand; cards: the ones it's dragging
let swallowUntil = 0;

/**
 * `start(code)` says which cards a drag of `code` carries (null: none, not now); `drop()` plays them
 * when they're let go over `area`. Anywhere else they go back.
 */
export function initDrag(hand, area, { start, drop }) {
  const rotated = () => document.getElementById('view-table').classList.contains('rotated');
  hand.addEventListener('dragstart', (event) => event.preventDefault()); // not the browser's own image drag
  hand.addEventListener('pointerdown', (event) => {
    const card = event.target.closest('.hand-card');
    if (!card || press || event.button !== 0) return;
    press = { id: event.pointerId, code: card.dataset.code, x: event.clientX, y: event.clientY, cards: null };
  });
  document.addEventListener('pointermove', (event) => {
    if (!press || event.pointerId !== press.id) return;
    const dx = event.clientX - press.x;
    const dy = event.clientY - press.y;
    if (!press.cards) {
      if (!isDrag(dx, dy)) return;
      const codes = start(press.code);
      if (!codes) {
        press = null;
        return;
      }
      press.cards = [...hand.querySelectorAll('.hand-card')].filter((el) => codes.includes(el.dataset.code));
      press.cards.forEach((el) => el.classList.add('dragging'));
      area.classList.add('drag-on');
    }
    const d = tableDelta(dx, dy, rotated());
    press.cards.forEach((el) => { el.style.transform = `translate(${d.x}px, ${d.y}px)`; });
    area.classList.toggle('drop-over', inside(area.getBoundingClientRect(), event.clientX, event.clientY));
  });
  const end = (event, cancelled) => {
    if (!press || event.pointerId !== press.id) return;
    const { cards } = press;
    press = null;
    if (!cards) return; // a tap: the click picks the card
    swallowUntil = performance.now() + SWALLOW_MS;
    const over = !cancelled && inside(area.getBoundingClientRect(), event.clientX, event.clientY);
    area.classList.remove('drag-on', 'drop-over');
    cards.forEach((el) => el.classList.remove('dragging'));
    if (!over) return goBack(cards);
    cards.forEach((el) => el.classList.add('dropped')); // they wait on the pile for the server's answer
    drop();
  };
  document.addEventListener('pointerup', (event) => end(event, false));
  document.addEventListener('pointercancel', (event) => end(event, true));
  hand.addEventListener('click', (event) => { // before the card's own click
    if (performance.now() >= swallowUntil) return;
    swallowUntil = 0;
    event.stopPropagation();
  }, true);
}

function goBack(cards) {
  cards.forEach((el) => {
    el.classList.remove('dropped');
    el.style.transform = '';
  });
}

/** Dropped cards the server turned down (or that never went out) slide back into your hand. */
export function settleDropped() {
  goBack([...document.querySelectorAll('.hand .hand-card.dropped')]);
}

/** Cards just dropped on the pile are already there: their play needn't slide in. */
export function justDropped() {
  return document.querySelector('.hand .hand-card.dropped') !== null;
}

/** Your hand is being redrawn: a drag of the old cards ends. */
export function cancelDrag() {
  if (!press?.cards) return;
  document.querySelector('.play-area')?.classList.remove('drag-on', 'drop-over');
  press = null;
}
