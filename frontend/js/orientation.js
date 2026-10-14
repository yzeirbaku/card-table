/** The table is a landscape layout; on a portrait viewport it is rotated 90° with CSS. */
export function shouldRotate(width, height) {
  return height > width;
}
