/** How to play: each game's text is a <template id="rules-<game id>"> in index.html. */
export function hasRules(gameId) {
  return document.getElementById(`rules-${gameId}`) !== null;
}

/** Put a game's rules into `body`, scrolled to the top. */
export function fillRules(body, gameId) {
  const text = document.getElementById(`rules-${gameId}`);
  body.replaceChildren(text ? text.content.cloneNode(true) : '');
  body.scrollTop = 0;
}
