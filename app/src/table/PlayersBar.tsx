import { useRef, type RefObject } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import type { PlayerView } from '../protocol';
import { colors } from '../theme';
import type { Rect } from './geometry';

export function measure(ref: RefObject<View | null>, cb: (r: Rect) => void) {
  ref.current?.measureInWindow((x, y, width, height) => cb({ x, y, width, height }));
}

function Avatar({ player, self, onRect }: { player: PlayerView; self: boolean; onRect: (r: Rect) => void }) {
  const ref = useRef<View>(null);
  return (
    <View
      ref={ref}
      onLayout={() => measure(ref, onRect)}
      style={[styles.chip, !player.connected && styles.away, self && styles.self]}
    >
      <Text style={styles.name} numberOfLines={1}>
        {player.is_host ? '👑 ' : ''}{self ? 'You' : player.name}
      </Text>
      <Text style={styles.count}>🂠 {player.hand_count}</Text>
    </View>
  );
}

export function PlayersBar({
  players, selfId, onAvatarRect,
}: { players: PlayerView[]; selfId: string | null; onAvatarRect: (playerId: string, r: Rect) => void }) {
  return (
    <View style={styles.bar}>
      {players.map((p) => (
        <Avatar key={p.id} player={p} self={p.id === selfId} onRect={(r) => onAvatarRect(p.id, r)} />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  bar: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, paddingHorizontal: 8, paddingVertical: 6 },
  chip: {
    flexDirection: 'row', alignItems: 'center', gap: 6, maxWidth: 160,
    backgroundColor: colors.felt, borderRadius: 16, paddingHorizontal: 10, paddingVertical: 8,
  },
  self: { borderWidth: 1, borderColor: colors.accent },
  away: { opacity: 0.4 },
  name: { color: colors.text, fontWeight: '600', flexShrink: 1 },
  count: { color: colors.muted, fontSize: 12 },
});
