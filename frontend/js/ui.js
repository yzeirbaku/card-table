const VIEWS = ['main', 'lobby', 'table'];
let toastTimer;

/** name = null hides every view (neutral state while resuming a saved room). */
export function showView(name) {
  for (const view of VIEWS) document.getElementById(`view-${view}`).hidden = view !== name;
  syncTableRotated();
}

/** Body class so toasts and the banner can turn with the rotated table. */
export function syncTableRotated() {
  const table = document.getElementById('view-table');
  document.body.classList.toggle('table-rotated', !table.hidden && table.classList.contains('rotated'));
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
