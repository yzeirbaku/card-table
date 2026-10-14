export function openSheet(id) {
  closeSheets();
  document.getElementById(id).hidden = false;
  document.getElementById('sheet-backdrop').hidden = false;
}

export function closeSheets() {
  document.querySelectorAll('.sheet').forEach((sheet) => { sheet.hidden = true; });
  document.getElementById('sheet-backdrop').hidden = true;
}
