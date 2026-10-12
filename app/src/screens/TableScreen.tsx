import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import * as Haptics from 'expo-haptics';
import Animated, { useAnimatedStyle, useSharedValue } from 'react-native-reanimated';
import { SafeAreaView } from 'react-native-safe-area-context';
import type { Action, CardView } from '../protocol';
import { colors } from '../theme';
import { useRoom } from '../useRoom';
import { CardFace } from '../table/CardFace';
import { toAction } from '../table/dropAction';
import { cardSize, HAND_TOP, handIndexAt, resolveDrop, type DragSource, type Rect } from '../table/geometry';
import { HandCardGestures, TopCardGestures, type DragHandlers } from '../table/gestures';
import { HandView } from '../table/HandView';
import { PileView } from '../table/PileView';
import { PileMenu, TableMenu, Toast } from '../table/menus';
import { measure, PlayersBar } from '../table/PlayersBar';

type Drag = { gesture: 'card' | 'pile'; source: DragSource; card: CardView; settling: boolean };

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

  const rootRef = useRef<View>(null);
  const rootX = useSharedValue(0);
  const rootY = useSharedValue(0);
  const dragX = useSharedValue(0);
  const dragY = useSharedValue(0);
  const [drag, setDrag] = useState<Drag | null>(null);
  const [menuPileId, setMenuPileId] = useState<string | null>(null);
  const [tableMenu, setTableMenu] = useState(false);

  // Gesture callbacks must be stable (they're captured by memoized gestures), so
  // they read the latest values through refs.
  const latest = useRef({ view, playerId, players, drag, send: room.send });
  latest.current = { view, playerId, players, drag, send: room.send };

  const send = useCallback((action: Action) => latest.current.send(action), []);

  // A dropped card stays where it landed until the server's answer arrives.
  useEffect(() => {
    setDrag((d) => (d?.settling ? null : d));
  }, [view]);
  useEffect(() => {
    if (!drag?.settling) return;
    const t = setTimeout(() => setDrag(null), 800);
    return () => clearTimeout(t);
  }, [drag?.settling]);

  const handlers: DragHandlers = useMemo(() => ({
    dragX,
    dragY,
    onCardStart: (pileId, cardId) => {
      const v = latest.current.view;
      if (!v || latest.current.drag) return;
      if (pileId === null) {
        const c = v.hand.find((h) => h.id === cardId);
        if (!c) return;
        setDrag({ gesture: 'card', source: { kind: 'card', cardId, fromPileId: null }, card: c, settling: false });
      } else {
        const pile = v.piles.find((p) => p.id === pileId);
        if (!pile) return;
        const top = pile.cards[pile.cards.length - 1];
        // A lone card moves as its pile, so nudging it doesn't count as "dropped on itself".
        const source: DragSource = pile.cards.length === 1
          ? { kind: 'pile', pileId }
          : { kind: 'card', cardId, fromPileId: pileId };
        setDrag({ gesture: 'card', source, card: top, settling: false });
      }
      void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    },
    onPileStart: (pileId) => {
      const v = latest.current.view;
      const pile = v?.piles.find((p) => p.id === pileId);
      if (!pile || latest.current.drag) return;
      setDrag({ gesture: 'pile', source: { kind: 'pile', pileId }, card: pile.cards[pile.cards.length - 1], settling: false });
      void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    },
    onEnd: (kind, x, y, success, moved) => {
      const { drag: d, view: v, playerId: self, players: ps } = latest.current;
      const { table, hand, avatars } = regions.current;
      if (!d || d.settling || d.gesture !== kind) return;
      if (!success || !v || !table || !hand) {
        setDrag(null);
        return;
      }
      if (kind === 'pile' && moved < 10 && d.source.kind === 'pile') {
        setDrag(null);
        setMenuPileId(d.source.pileId);
        return;
      }
      const card = cardSize(table.width);
      const liveAvatars = ps.flatMap((p) => {
        const rect = avatars.get(p.id);
        return rect ? [{ playerId: p.id, rect }] : [];
      });
      const target = resolveDrop({ x, y }, d.source, { table, hand, avatars: liveAvatars }, v.piles, self, card);
      const fromHand = d.source.kind === 'card' && d.source.fromPileId === null;
      const slots = v.hand.length + (fromHand ? 0 : 1);
      const action = toAction(d.source, target, v.piles, handIndexAt(x, slots, hand, card));
      if (!action) {
        setDrag(null);
        return;
      }
      send(action);
      void Haptics.selectionAsync();
      dragX.value = x;
      dragY.value = y;
      setDrag({ ...d, settling: true });
    },
    onFlip: (cardId) => {
      send({ type: 'flip_card', card_id: cardId });
      void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    },
  }), [dragX, dragY, send]);

  const overlayStyle = useAnimatedStyle(() => ({
    transform: [
      { translateX: dragX.value - rootX.value - card.width / 2 },
      { translateY: dragY.value - rootY.value - card.height / 2 },
      { scale: 1.08 },
    ],
  }), [card.width, card.height]);

  const hiddenCardId = drag?.source.kind === 'card' ? drag.source.cardId : null;
  const hiddenPileId = drag?.source.kind === 'pile' ? drag.source.pileId : null;

  const leaveRoom = () => {
    room.leave();
    onExit();
  };

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
      <View
        ref={rootRef}
        style={styles.root}
        onLayout={() => measure(rootRef, (r) => { rootX.value = r.x; rootY.value = r.y; })}
      >
        <View style={styles.header}>
          <Text style={styles.code}>{code}</Text>
          <Text style={styles.status}>
            {room.status === 'reconnecting' ? 'Reconnecting…' : room.status === 'connecting' ? 'Connecting…' : ''}
          </Text>
          <Pressable onPress={() => setTableMenu(true)} hitSlop={12}>
            <Text style={styles.link}>☰</Text>
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
              <PileView
                key={p.id}
                pile={p}
                table={tableSize}
                card={card}
                hidden={p.id === hiddenPileId}
                hiddenCardId={hiddenCardId}
                topSlot={(top) => (
                  <TopCardGestures pileId={p.id} cardId={p.cards[p.cards.length - 1].id} h={handlers}>
                    {top}
                  </TopCardGestures>
                )}
              />
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
          <HandView
            cards={view?.hand ?? []}
            width={handWidth}
            card={card}
            hiddenCardId={hiddenCardId}
            wrapCard={(c, node) => <HandCardGestures cardId={c.id} h={handlers}>{node}</HandCardGestures>}
          />
        </View>
        {drag && (
          <Animated.View pointerEvents="none" style={[styles.overlay, overlayStyle]}>
            <CardFace card={drag.card} size={card} />
          </Animated.View>
        )}
        <Toast error={room.lastError} />
        <PileMenu
          pile={view?.piles.find((p) => p.id === menuPileId) ?? null}
          onAction={send}
          onClose={() => setMenuPileId(null)}
        />
        <TableMenu visible={tableMenu} onAction={send} onLeave={leaveRoom} onClose={() => setTableMenu(false)} />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.feltDark },
  root: { flex: 1 },
  centered: { alignItems: 'center', justifyContent: 'center', gap: 16, padding: 24 },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 12, paddingTop: 4, gap: 12 },
  code: { color: colors.text, fontSize: 26, fontWeight: '800', letterSpacing: 4 },
  status: { flex: 1, color: colors.accent },
  link: { color: colors.accent, fontSize: 17, fontWeight: '600' },
  fatal: { color: colors.text, fontSize: 18, textAlign: 'center' },
  table: { flex: 1, backgroundColor: colors.felt, marginHorizontal: 8, borderRadius: 16 },
  hand: { marginHorizontal: 8, marginTop: 8 },
  overlay: {
    position: 'absolute', left: 0, top: 0,
    shadowColor: '#000', shadowOpacity: 0.4, shadowRadius: 8, shadowOffset: { width: 0, height: 6 },
  },
});
