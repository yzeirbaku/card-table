// A plain (not module) script at the top of <body>: it puts the saved table and card style on
// before the page first draws, so the defaults never flash. app.js checks the values and
// sets the card pictures.
try {
  const { theme, cardStyle } = JSON.parse(localStorage.getItem('card-table')) ?? {};
  if (/^[a-z]+$/.test(theme ?? '')) document.body.classList.replace('theme-classic', `theme-${theme}`);
  if (/^[a-z]+$/.test(cardStyle ?? '')) document.body.classList.replace('cards-traditional', `cards-${cardStyle}`);
} catch {
  // no saved settings, or storage is blocked: the defaults stay
}
