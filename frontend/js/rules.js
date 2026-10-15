/** How to play: the one text in index.html's template, copied into the main-screen sheet and the table popup. */
export function fillRules() {
  const text = document.getElementById('rules-murlan').content;
  for (const body of document.querySelectorAll('.rules-body')) body.replaceChildren(text.cloneNode(true));
}
