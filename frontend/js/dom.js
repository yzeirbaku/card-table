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

let preloaded = []; // held on to, so the browser keeps the pictures ready
let cardStyle = 'traditional';

/** Switch every face-up card, shown now or later, to a card style's pictures, and fetch that
 *  style's pictures up front: a card seen for the first time (someone's play) then shows at
 *  once, instead of its empty frame flashing on the pile while the picture downloads. */
export function useCardStyle(style) {
  cardStyle = style;
  for (const img of document.querySelectorAll('img[data-card]')) img.src = cardImage(img.dataset.card, style);
  preloaded = ALL_CARDS.map((code) => {
    const img = new Image();
    img.src = cardImage(code, style);
    img.decode().catch(() => {}); // a picture that fails to load is just fetched again when shown
    return img;
  });
}

/** A face-up card, in the same .card-face wrapper the card styles (Vintage) apply to. */
export function face(code, className = '') {
  const wrap = span('', `card-face ${className}`.trim());
  const img = document.createElement('img');
  img.dataset.card = code;
  img.src = cardImage(code, cardStyle);
  img.alt = cardName(code);
  wrap.append(img);
  return wrap;
}
