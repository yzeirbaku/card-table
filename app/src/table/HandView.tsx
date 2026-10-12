import type { ReactNode } from 'react';
import { View } from 'react-native';
import type { CardView } from '../protocol';
import { CardFace } from './CardFace';
import { HAND_PADDING, HAND_TOP, handStep, type Size } from './geometry';

type Props = {
  cards: CardView[];
  width: number;
  card: Size;
  hiddenCardId: string | null;
  wrapCard?: (c: CardView, node: ReactNode) => ReactNode;
};

export function HandView({ cards, width, card, hiddenCardId, wrapCard }: Props) {
  const step = handStep(cards.length, width, card);
  return (
    <>
      {cards.map((c, i) => {
        const node = (
          <View
            key={c.id}
            style={{ position: 'absolute', left: HAND_PADDING + i * step, top: HAND_TOP, opacity: c.id === hiddenCardId ? 0 : 1 }}
          >
            <CardFace card={c} size={card} />
          </View>
        );
        return wrapCard ? <View key={c.id}>{wrapCard(c, node)}</View> : node;
      })}
    </>
  );
}
