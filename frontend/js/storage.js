const KEY = 'card-table';
export const THEMES = ['classic', 'qendisje', 'kafeneio', 'scoarta', 'kahvehane', 'julehjerte'];
export const CARD_STYLES = ['traditional', 'vintage', 'atlas', 'modern'];

/** Everything the device remembers: name, settings, seat tokens per room, the room you're in. */
export function createStore(storage = globalThis.localStorage) {
  const read = () => {
    try {
      const data = JSON.parse(storage.getItem(KEY));
      return data && typeof data === 'object' ? data : {};
    } catch {
      return {};
    }
  };
  const update = (patch) => storage.setItem(KEY, JSON.stringify({ ...read(), ...patch }));

  return {
    getName: () => read().name ?? '',
    setName: (name) => update({ name }),
    getSettings() {
      const { theme, cardStyle } = read();
      return {
        theme: THEMES.includes(theme) ? theme : THEMES[0],
        cardStyle: CARD_STYLES.includes(cardStyle) ? cardStyle : CARD_STYLES[0],
      };
    },
    setSettings: (patch) => update(patch),
    getToken: (code) => read().tokens?.[code] ?? null,
    setToken: (code, token) => update({ tokens: { ...read().tokens, [code]: token } }),
    clearToken(code) {
      const tokens = { ...read().tokens };
      delete tokens[code];
      update({ tokens });
    },
    getCurrentRoom: () => read().room ?? null,
    setCurrentRoom: (code) => update({ room: code }),
  };
}
