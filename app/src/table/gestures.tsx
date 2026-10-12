import { useMemo, type ReactNode } from 'react';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import { runOnJS, type SharedValue } from 'react-native-reanimated';

export type DragHandlers = {
  dragX: SharedValue<number>;
  dragY: SharedValue<number>;
  onCardStart: (pileId: string | null, cardId: string) => void;
  onPileStart: (pileId: string) => void;
  onEnd: (kind: 'card' | 'pile', key: string, x: number, y: number, success: boolean, moved: number) => void;
  onFlip: (cardId: string) => void;
};

const LONG_PRESS_MS = 350;

function cardPan(h: DragHandlers, pileId: string | null, cardId: string) {
  const { dragX, dragY, onCardStart, onEnd } = h;
  return Gesture.Pan()
    .minDistance(6)
    .onStart((e) => {
      dragX.value = e.absoluteX;
      dragY.value = e.absoluteY;
      runOnJS(onCardStart)(pileId, cardId);
    })
    .onUpdate((e) => {
      dragX.value = e.absoluteX;
      dragY.value = e.absoluteY;
    })
    .onEnd((e, success) => {
      runOnJS(onEnd)('card', cardId, e.absoluteX, e.absoluteY, success, Math.hypot(e.translationX, e.translationY));
    });
}

export function TopCardGestures({
  pileId, cardId, h, children,
}: { pileId: string; cardId: string; h: DragHandlers; children: ReactNode }) {
  const gesture = useMemo(() => {
    const { dragX, dragY, onPileStart, onEnd, onFlip } = h;
    // Long-press then drag moves the whole pile; long-press without moving opens its menu.
    const pilePan = Gesture.Pan()
      .activateAfterLongPress(LONG_PRESS_MS)
      .onStart((e) => {
        dragX.value = e.absoluteX;
        dragY.value = e.absoluteY;
        runOnJS(onPileStart)(pileId);
      })
      .onUpdate((e) => {
        dragX.value = e.absoluteX;
        dragY.value = e.absoluteY;
      })
      .onEnd((e, success) => {
        runOnJS(onEnd)('pile', pileId, e.absoluteX, e.absoluteY, success, Math.hypot(e.translationX, e.translationY));
      });
    const tap = Gesture.Tap()
      .maxDuration(250)
      .onEnd((_e, success) => {
        if (success) runOnJS(onFlip)(cardId);
      });
    return Gesture.Race(pilePan, cardPan(h, pileId, cardId), tap);
  }, [pileId, cardId, h]);
  return <GestureDetector gesture={gesture}>{children}</GestureDetector>;
}

export function HandCardGestures({ cardId, h, children }: { cardId: string; h: DragHandlers; children: ReactNode }) {
  const gesture = useMemo(() => cardPan(h, null, cardId), [cardId, h]);
  return <GestureDetector gesture={gesture}>{children}</GestureDetector>;
}
