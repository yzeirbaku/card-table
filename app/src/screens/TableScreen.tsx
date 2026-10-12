import { useCallback, useRef, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { colors } from '../theme';
import { useRoom } from '../useRoom';
import { cardSize, HAND_TOP, type Rect } from '../table/geometry';
import { HandView } from '../table/HandView';
import { PileView } from '../table/PileView';
import { measure, PlayersBar } from '../table/PlayersBar';

export default function TableScreen({ code, name, onExit }: { code: string; name: string; onExit: () => void }) {
  const room = useRoom(code, name);
  const { view, players, playerId } = room;

  const tableRef = useRef<View>(null);
  const handRef = useRef<View>(null);
  const regions = useRef<{ table: Rect | null; hand: Rect | null; avatars: Map<string, Rect> }>({
    table: null, hand: null, avatars: new Map(),
  });
  const [tableSize, setTableSize] = useState({ width: 0, height: 0 });
  const [handWidth, setHandWidth] = useState(0);
  const card = cardSize(tableSize.width || 360);

  const onAvatarRect = useCallback((id: string, r: Rect) => regions.current.avatars.set(id, r), []);

  if (room.fatal) {
    return (
      <SafeAreaView style={[styles.screen, styles.centered]}>
        <Text style={styles.fatal}>{room.fatal}</Text>
        <Pressable onPress={onExit}><Text style={styles.link}>Back</Text></Pressable>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.screen} edges={['top', 'bottom']}>
      <View style={styles.header}>
        <Text style={styles.code}>{code}</Text>
        <Text style={styles.status}>{room.status === 'reconnecting' ? 'Reconnecting…' : ''}</Text>
        <Pressable onPress={() => { room.leave(); onExit(); }}>
          <Text style={styles.link}>Leave</Text>
        </Pressable>
      </View>
      <PlayersBar players={players} selfId={playerId} onAvatarRect={onAvatarRect} />
      <View
        ref={tableRef}
        style={styles.table}
        onLayout={(e) => {
          setTableSize({ width: e.nativeEvent.layout.width, height: e.nativeEvent.layout.height });
          measure(tableRef, (r) => { regions.current.table = r; });
        }}
      >
        {tableSize.width > 0 &&
          view?.piles.map((p) => (
            <PileView key={p.id} pile={p} table={tableSize} card={card} hidden={false} hiddenCardId={null} />
          ))}
      </View>
      <View
        ref={handRef}
        style={[styles.hand, { height: card.height + HAND_TOP * 2 }]}
        onLayout={(e) => {
          setHandWidth(e.nativeEvent.layout.width);
          measure(handRef, (r) => { regions.current.hand = r; });
        }}
      >
        <HandView cards={view?.hand ?? []} width={handWidth} card={card} hiddenCardId={null} />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.feltDark },
  centered: { alignItems: 'center', justifyContent: 'center', gap: 16, padding: 24 },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 12, paddingTop: 4, gap: 12 },
  code: { color: colors.text, fontSize: 26, fontWeight: '800', letterSpacing: 4 },
  status: { flex: 1, color: colors.accent },
  link: { color: colors.accent, fontSize: 17, fontWeight: '600' },
  fatal: { color: colors.text, fontSize: 18, textAlign: 'center' },
  table: { flex: 1, backgroundColor: colors.felt, marginHorizontal: 8, borderRadius: 16 },
  hand: { marginHorizontal: 8, marginTop: 8 },
});
