import * as SecureStore from 'expo-secure-store';

// Storage failures are never fatal: worst case you rejoin as a new seat.
const seatKey = (code: string) => `seat_${code}`;

export async function loadSeat(code: string): Promise<string | null> {
  try { return await SecureStore.getItemAsync(seatKey(code)); } catch { return null; }
}
export async function saveSeat(code: string, token: string): Promise<void> {
  try { await SecureStore.setItemAsync(seatKey(code), token); } catch { /* ignore */ }
}
export async function clearSeat(code: string): Promise<void> {
  try { await SecureStore.deleteItemAsync(seatKey(code)); } catch { /* ignore */ }
}
export async function loadName(): Promise<string | null> {
  try { return await SecureStore.getItemAsync('name'); } catch { return null; }
}
export async function saveName(name: string): Promise<void> {
  try { await SecureStore.setItemAsync('name', name); } catch { /* ignore */ }
}
