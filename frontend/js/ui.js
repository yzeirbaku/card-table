const VIEWS = ['main', 'lobby', 'table'];
const FELT = '#123d25'; // the felt's darkest green, as in index.html and the manifest
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
  // Whatever shows past the page (an installed app's system bars, the strip an iPhone leaves under it)
  // takes the colour at the page's edge: the table's edge at the table, the felt elsewhere.
  const edge = table.hidden ? '' : getComputedStyle(table).backgroundColor;
  document.documentElement.style.backgroundColor = edge;
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', edge || FELT);
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
