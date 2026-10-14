import { cardImage, cardName } from './murlan.js';

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

/** A face-up card, in the same .card-face wrapper the card styles (Vintage) apply to. */
export function face(code, className = '') {
  const wrap = span('', `card-face ${className}`.trim());
  const img = document.createElement('img');
  img.src = cardImage(code);
  img.alt = cardName(code);
  wrap.append(img);
  return wrap;
}
