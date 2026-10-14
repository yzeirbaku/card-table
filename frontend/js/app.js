import { initMain } from './main-view.js';
import { closeSheets } from './sheets.js';
import { createStore } from './storage.js';
import { toast } from './ui.js';

const store = createStore();

function applySettings({ theme, cardStyle }) {
  document.body.className = `theme-${theme} cards-${cardStyle}`;
}

applySettings(store.getSettings());
initMain({ store, applySettings, enterRoom: (code) => toast(`Table ${code}: lobby comes in the next task`) });
document.getElementById('sheet-backdrop').addEventListener('click', closeSheets);
