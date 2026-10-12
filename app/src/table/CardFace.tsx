import { StyleSheet, Text, View } from 'react-native';
import type { CardView } from '../protocol';
import { colors } from '../theme';
import type { Size } from './geometry';

const SUIT_SYMBOL = { S: '♠', H: '♥', D: '♦', C: '♣' } as const;

export function CardFace({ card, size }: { card: CardView; size: Size }) {
  const box = { width: size.width, height: size.height, borderRadius: size.width * 0.1 };
  if (!card.face_up || !card.rank) {
    return (
      <View style={[styles.back, box]}>
        <View style={[styles.backInner, { borderRadius: size.width * 0.07 }]} />
      </View>
    );
  }
  const joker = card.rank === 'JOKER';
  const red = card.suit === 'H' || card.suit === 'D';
  const color = joker ? colors.accent : red ? colors.cardRed : colors.cardBlack;
  const symbol = card.suit ? SUIT_SYMBOL[card.suit] : '★';
  return (
    <View style={[styles.face, box]}>
      <Text style={[styles.corner, { color, fontSize: size.width * 0.26 }]}>{joker ? 'JKR' : card.rank}</Text>
      <Text style={[styles.center, { color, fontSize: size.width * 0.45 }]}>{symbol}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  face: {
    backgroundColor: colors.cardFace, padding: 4,
    borderWidth: StyleSheet.hairlineWidth, borderColor: '#0003',
    shadowColor: '#000', shadowOpacity: 0.25, shadowRadius: 2, shadowOffset: { width: 0, height: 1 },
  },
  corner: { fontWeight: '700' },
  center: { position: 'absolute', alignSelf: 'center', top: '35%' },
  back: {
    backgroundColor: colors.cardBack, padding: 4,
    borderWidth: 2, borderColor: colors.cardFace,
    shadowColor: '#000', shadowOpacity: 0.25, shadowRadius: 2, shadowOffset: { width: 0, height: 1 },
  },
  backInner: { flex: 1, backgroundColor: colors.cardBackInner },
});
