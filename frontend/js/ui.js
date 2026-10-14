const VIEWS = ['main', 'lobby', 'table'];
let toastTimer;

export function showView(name) {
  for (const view of VIEWS) document.getElementById(`view-${view}`).hidden = view !== name;
}

export function toast(message) {
  const el = document.getElementById('toast');
  el.textContent = message;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 3500);
}

export function setReconnecting(on) {
  document.getElementById('banner').hidden = !on;
}
