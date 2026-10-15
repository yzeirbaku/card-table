import { button, div, face, span } from './dom.js';
import { formatClock, placeLabel, sideName } from './murlan.js';

let countdown = null; // ticks the pause clock between server updates

/** Stop the pause clock when the table goes away. */
export function stopCountdown() {
  clearInterval(countdown);
}

/** The panel over the table for whatever needs attention right now, or nothing. */
export function renderOverlay(el, game, meId, names, send) {
  clearInterval(countdown);
  const ctx = { game, meId, names, send, act: (action) => send({ type: 'action', action }) };
  const content = game.pause ? paused(ctx) : PHASES[game.phase]?.(ctx);
  el.hidden = !content;
  el.replaceChildren(...(content ?? []));
}

const PHASES = {
  choosing_target: target,
  cutting,
  agreeing_loser: agreeing,
  game_over: gameOver,
};

function target({ game, meId, names, act }) {
  if (game.creator !== meId) return [title('Murlan'), text(`Waiting for ${names[game.creator]} to choose the target…`)];
  return [
    title('Play to'),
    row(...[5, 10, 13, 21].map((n) => button(String(n), () => act({ type: 'choose_target', target: n })))),
  ];
}

function cutting({ game, meId, names, act }) {
  const { cutter, deck_size: size, card } = game.cut;
  const result = lastRound(game, names);
  if (cutter !== meId) return [...result, text(`${names[cutter]} is cutting…`)];
  if (card) {
    return [title('Your card'), face(card, 'cut-pick'),
      row(button('Take it', () => act({ type: 'take_cut', take: true }), 'on'),
        button('Leave it', () => act({ type: 'take_cut', take: false })))];
  }
  const deck = div('cut-deck');
  for (let i = 0; i < size; i++) deck.append(button('', () => act({ type: 'cut', index: i }), 'cut-card'));
  return [title('Cut the deck'), text('Tap anywhere in the deck'), deck]; // just the deck, so it fits a phone
}

function agreeing({ game, meId, names, act }) {
  const { voters, picks } = game.agree;
  if (!voters.includes(meId)) {
    return [title('Round over'), text(`${names[voters[0]]} and ${names[voters[1]]} are choosing who's last…`)];
  }
  const partner = voters.find((id) => id !== meId);
  const theirs = picks[partner];
  const said = theirs ? `${names[partner]} picked ${theirs === meId ? 'you' : 'themselves'}` : `${names[partner]} hasn't picked yet`;
  return [
    title("Who's last?"),
    text(said),
    row(...voters.map((id) => button(id === meId ? 'Me' : names[id],
      () => { if (picks[meId] !== id) act({ type: 'pick_loser', player_id: id }); }, // already picked: nothing to send
      picks[meId] === id ? 'on' : ''))),
  ];
}

function gameOver({ game, meId, names, send }) {
  const side = game.winner_side === null ? null : game.sides[game.winner_side];
  const head = side ? `${sideName(side, names)} ${side.players.length > 1 ? 'win' : 'wins'}!` : "It's a draw";
  const items = [title(head), scores(game, names)];
  if (game.decider !== meId) return [...items, text(`Waiting for ${names[game.decider]} to choose…`)];
  const choose = (choice) => send({ type: 'after_game', choice });
  const buttons = [button('Play again', () => choose('play_again'), 'on')];
  if (game.seats.length === 4) buttons.push(button('Shuffle teams', () => choose('shuffle_teams')));
  buttons.push(button('Back to the lobby', () => choose('lobby')));
  return [...items, column(...buttons)];
}

function paused({ game, meId, names, act }) {
  const { pause } = game;
  const who = pause.waiting_for.map((id) => names[id]).join(' and ');
  if (pause.timed_out && !pause.keep_waiting) {
    const items = [title('Round cancelled'), text(`${who} didn't come back in time.`)];
    if (game.decider !== meId) return [...items, text(`Waiting for ${names[game.decider]} to decide…`)];
    return [...items, row(
      button('Keep waiting', () => act({ type: 'decide', choice: 'keep_waiting' }), 'on'),
      button('End game', () => act({ type: 'decide', choice: 'end_game' })),
    )];
  }
  if (pause.seconds_left === null) {
    const items = [title('Paused'), text(`Waiting for ${who} to come back…`)];
    if (pause.keep_waiting && game.decider === meId) {
      items.push(row(button('End game', () => act({ type: 'decide', choice: 'end_game' }))));
    }
    return items;
  }
  const clock = span(formatClock(pause.seconds_left), 'countdown');
  const ends = Date.now() + pause.seconds_left * 1000;
  countdown = setInterval(() => { clock.textContent = formatClock((ends - Date.now()) / 1000); }, 500);
  return [title('Paused'), text(`${who} disconnected, waiting…`), clock];
}

function lastRound(game, names) {
  const result = game.last_round;
  if (!result) return [];
  const order = result.places.map((id, i) => `${placeLabel(i)} ${names[id]}`).join(' · ');
  return [title(`Round ${game.round - 1}`), text(order), scores(game, names)];
}

function scores(game, names) {
  const list = div('score-list');
  for (const side of game.sides) {
    const line = div();
    line.append(span(sideName(side, names)), span(String(side.score)));
    list.append(line);
  }
  if (game.target) list.append(span(`Race to ${game.target}`, 'score-target'));
  return list;
}

/** First cards after "Take it", or the swap between partners: everyone sees them for a few seconds. */
export function renderReveal(el, game, names) {
  const reveal = game.reveal;
  el.hidden = !reveal;
  if (!reveal) return el.replaceChildren();
  const swap = reveal.kind === 'swap';
  const jokers = reveal.kind === 'jokers';
  const items = Object.entries(reveal.cards).map(([id, codes]) => {
    const item = div('reveal-item');
    const cards = div('reveal-cards');
    cards.append(...codes.map((code) => face(code)));
    item.append(cards, span(swap ? `${names[id]} gave` : jokers ? `${names[id]} has both jokers` : names[id]));
    return item;
  });
  const heading = swap ? 'The swap' : jokers ? 'No swap' : 'First cards';
  el.replaceChildren(span(heading, 'reveal-title'), ...items);
}

function title(value) {
  const el = document.createElement('h2');
  el.textContent = value;
  return el;
}

function text(value) {
  const el = document.createElement('p');
  el.textContent = value;
  return el;
}

function row(...children) {
  const el = div('choice-row');
  el.append(...children);
  return el;
}

function column(...children) {
  const el = div('overlay-buttons');
  el.append(...children);
  return el;
}
