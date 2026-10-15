/** The table is a landscape layout; on a portrait viewport it is rotated 90° with CSS. */
export function shouldRotate(width, height) {
  return height > width;
}

/**
 * The size the app really has. An iPhone home-screen app that draws under the status bar reports a
 * viewport that's short by the status bar's height, so "full height" stops above the bottom of the
 * screen. There, the screen's own size (portrait numbers, whichever way the phone is held) is the truth.
 */
export function appSize({ standalone, innerWidth, innerHeight, screenWidth, screenHeight }) {
  if (!standalone) return { width: innerWidth, height: innerHeight };
  const long = Math.max(screenWidth, screenHeight);
  const short = Math.min(screenWidth, screenHeight);
  const [width, height] = innerWidth > innerHeight ? [long, short] : [short, long];
  return { width: Math.max(innerWidth, width), height: Math.max(innerHeight, height) };
}
