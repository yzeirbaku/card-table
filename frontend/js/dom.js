import { ALL_CARDS, cardImage, cardName } from './murlan.js';

// Tiny DOM builders. Text always goes in through textContent.

export function div(className = '') {
  const el = document.createElement('div');
  el.className = className;
  return el;
}

export function span(text, className = '') {
  const el = document.createElement('span');
  el.className = className;
  el.textContent = text;
  return el;
}

export function button(label, onClick, className = '') {
  const el = document.createElement('button');
  el.type = 'button';
  el.className = className;
  el.textContent = label;
  el.addEventListener('click', onClick);
  return el;
}

const preloaded = []; // held on to, so the browser keeps the pictures ready

/** Fetch every card picture up front: a card seen for the first time (someone's play) then shows at
 *  once, instead of its empty frame flashing on the pile while the picture downloads. */
export function preloadCards() {
  for (const code of ALL_CARDS) {
    const img = new Image();
    img.src = cardImage(code);
    img.decode().catch(() => {}); // a picture that fails to load is just fetched again when shown
    preloaded.push(img);
  }
}

/** A face-up card, in the same .card-face wrapper the card styles (Vintage) apply to. */
export function face(code, className = '') {
  const wrap = span('', `card-face ${className}`.trim());
  const img = document.createElement('img');
  img.src = cardImage(code);
  img.alt = cardName(code);
  wrap.append(img);
  return wrap;
}
