import type { ReactNode } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import type { PileView as Pile } from '../protocol';
import { colors } from '../theme';
import { CardFace } from './CardFace';
import { fanStep, pileOffset, type Size } from './geometry';

export type PileViewProps = {
  pile: Pile;
  table: Size;
  card: Size;
  hidden: boolean; // whole pile is being dragged
  hiddenCardId: string | null; // top card is being dragged
  topSlot?: (top: ReactNode) => ReactNode;
};

export function PileView({ pile, table, card, hidden, hiddenCardId, topSlot }: PileViewProps) {
  const box = pileOffset(pile, table, card);
  const step = fanStep(pile, table.width, card);
  const topIndex = pile.cards.length - 1;
  const top = pile.cards[topIndex];

  const topNode = (
    <View style={{ position: 'absolute', left: topIndex * step, opacity: hiddenCardId === top.id ? 0 : 1 }}>
      <CardFace card={top} size={card} />
    </View>
  );

  return (
    <View
      pointerEvents="box-none"
      style={{ position: 'absolute', left: box.x, top: box.y, width: box.width, height: box.height, opacity: hidden ? 0 : 1 }}
    >
      {pile.layout === 'fan'
        ? pile.cards.slice(0, -1).map((c, i) => (
            <View key={c.id} style={{ position: 'absolute', left: i * step }}>
              <CardFace card={c} size={card} />
            </View>
          ))
        : topIndex > 0 && (
            <View style={{ position: 'absolute', left: 2, top: 2 }}>
              <CardFace card={pile.cards[topIndex - 1]} size={card} />
            </View>
          )}
      {topSlot ? topSlot(topNode) : topNode}
      {pile.layout === 'stack' && pile.cards.length > 1 && (
        <Text pointerEvents="none" style={styles.count}>{pile.cards.length}</Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  count: {
    position: 'absolute', right: -6, bottom: -6, minWidth: 22, textAlign: 'center',
    backgroundColor: colors.feltDark, color: colors.text, fontSize: 12, fontWeight: '700',
    borderRadius: 11, paddingHorizontal: 4, overflow: 'hidden',
  },
});
