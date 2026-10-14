export const CODE_LENGTH = 4;

/** Room codes are 4 letters; accept whatever was typed or pasted and keep just that. */
export function cleanCode(input) {
  return input.toUpperCase().replace(/[^A-Z]/g, '').slice(0, CODE_LENGTH);
}

export function isCompleteCode(code) {
  return /^[A-Z]{4}$/.test(code);
}
