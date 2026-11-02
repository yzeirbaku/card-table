const VIEWS = ['main', 'lobby', 'table', 'profile'];
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
  // takes the colour at the page's edge: the table's edge at the table, the felt elsewhere. Always set
  // outright: an iPhone kept the table's brown after a cleared colour on the way back to the felt.
  const edge = getComputedStyle(table.hidden ? document.getElementById('view-main') : table).backgroundColor; // the felt under the main view's gradient
  document.documentElement.style.backgroundColor = edge;
  document.body.style.backgroundColor = edge;
  document.getElementById('status-tint').style.backgroundColor = faint(edge);
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', edge);
}

/** "rgb(91, 58, 30)" -> "rgba(91, 58, 30, 0.05)": the colour, all but see-through. */
function faint(color) {
  const [r, g, b] = color.match(/[\d.]+/g) ?? [0, 0, 0];
  return `rgba(${r}, ${g}, ${b}, 0.05)`;
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

/** A question over whatever page is up. Resolves true only when `go` is tapped; `stay` is the gold default. */
export function askConfirm({ title, text, stay, go }) {
  const box = document.getElementById('page-confirm');
  const stayBtn = document.getElementById('btn-page-confirm-stay');
  const goBtn = document.getElementById('btn-page-confirm-go');
  document.getElementById('page-confirm-title').textContent = title;
  document.getElementById('page-confirm-text').textContent = text;
  stayBtn.textContent = stay;
  goBtn.textContent = go;
  box.hidden = false;
  stayBtn.focus();
  return new Promise((resolve) => {
    const finish = (answer) => {
      box.hidden = true;
      stayBtn.removeEventListener('click', onStay);
      goBtn.removeEventListener('click', onGo);
      box.removeEventListener('click', onBackdrop);
      resolve(answer);
    };
    const onStay = () => finish(false);
    const onGo = () => finish(true);
    const onBackdrop = (event) => { if (event.target === box) finish(false); };
    stayBtn.addEventListener('click', onStay);
    goBtn.addEventListener('click', onGo);
    box.addEventListener('click', onBackdrop);
  });
}
