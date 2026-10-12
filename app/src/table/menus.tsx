import { useEffect, useState, type ReactNode } from 'react';
import { Modal, Pressable, StyleSheet, Text, View } from 'react-native';
import * as Haptics from 'expo-haptics';
import type { Action, PileView } from '../protocol';
import { colors } from '../theme';

function Sheet({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  return (
    <Modal transparent animationType="fade" visible onRequestClose={onClose}>
      <Pressable style={styles.backdrop} onPress={onClose}>
        <Pressable style={styles.sheet}>
          <Text style={styles.title}>{title}</Text>
          {children}
          <MenuButton label="Cancel" subtle onPress={onClose} />
        </Pressable>
      </Pressable>
    </Modal>
  );
}

function MenuButton({ label, onPress, subtle, danger }: { label: string; onPress: () => void; subtle?: boolean; danger?: boolean }) {
  return (
    <Pressable style={({ pressed }) => [styles.button, subtle && styles.subtle, pressed && styles.pressed]} onPress={onPress}>
      <Text style={[styles.buttonText, danger && { color: colors.danger }]}>{label}</Text>
    </Pressable>
  );
}

export function PileMenu({ pile, onAction, onClose }: { pile: PileView | null; onAction: (a: Action) => void; onClose: () => void }) {
  const [deal, setDeal] = useState(1);
  if (!pile) return null;
  const run = (a: Action) => {
    onAction(a);
    onClose();
  };
  return (
    <Sheet title={`Pile · ${pile.cards.length} card${pile.cards.length === 1 ? '' : 's'}`} onClose={onClose}>
      <MenuButton
        label="Shuffle"
        onPress={() => {
          void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
          run({ type: 'shuffle', pile_id: pile.id });
        }}
      />
      <MenuButton label="Flip pile over" onPress={() => run({ type: 'flip_pile', pile_id: pile.id })} />
      <MenuButton
        label={pile.layout === 'stack' ? 'Fan out' : 'Stack up'}
        onPress={() => run({ type: 'set_layout', pile_id: pile.id, layout: pile.layout === 'stack' ? 'fan' : 'stack' })}
      />
      <View style={styles.row}>
        <Pressable style={styles.step} onPress={() => setDeal((d) => Math.max(1, d - 1))}><Text style={styles.buttonText}>−</Text></Pressable>
        <View style={{ flex: 1 }}>
          <MenuButton label={`Deal ${deal} to each`} onPress={() => run({ type: 'deal', pile_id: pile.id, count: deal })} />
        </View>
        <Pressable style={styles.step} onPress={() => setDeal((d) => Math.min(26, d + 1))}><Text style={styles.buttonText}>+</Text></Pressable>
      </View>
      <MenuButton label="Take all into hand" onPress={() => run({ type: 'take_pile', pile_id: pile.id })} />
    </Sheet>
  );
}

export function TableMenu({
  visible, onAction, onLeave, onClose,
}: { visible: boolean; onAction: (a: Action) => void; onLeave: () => void; onClose: () => void }) {
  if (!visible) return null;
  const run = (a: Action) => {
    onAction(a);
    onClose();
  };
  return (
    <Sheet title="Table" onClose={onClose}>
      <MenuButton label="Gather everything & shuffle" onPress={() => run({ type: 'gather' })} />
      <MenuButton label="New deck (no jokers)" onPress={() => run({ type: 'new_deck', jokers: 0 })} />
      <MenuButton label="New deck (+2 jokers)" onPress={() => run({ type: 'new_deck', jokers: 2 })} />
      <MenuButton label="Leave room" danger onPress={onLeave} />
    </Sheet>
  );
}

export function Toast({ error }: { error: { message: string; at: number } | null }) {
  const [shown, setShown] = useState<string | null>(null);
  useEffect(() => {
    if (!error) return;
    setShown(error.message);
    void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
    const t = setTimeout(() => setShown(null), 2000);
    return () => clearTimeout(t);
  }, [error]);
  if (!shown) return null;
  return (
    <View pointerEvents="none" style={styles.toast}>
      <Text style={styles.toastText}>{shown}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: '#0008', justifyContent: 'flex-end' },
  sheet: { backgroundColor: colors.sheet, padding: 16, paddingBottom: 32, gap: 8, borderTopLeftRadius: 20, borderTopRightRadius: 20 },
  title: { color: colors.muted, textAlign: 'center', marginBottom: 4 },
  button: { backgroundColor: colors.felt, borderRadius: 12, paddingVertical: 14, alignItems: 'center' },
  subtle: { backgroundColor: 'transparent' },
  pressed: { opacity: 0.6 },
  buttonText: { color: colors.text, fontSize: 17, fontWeight: '600' },
  row: { flexDirection: 'row', gap: 8, alignItems: 'center' },
  step: { backgroundColor: colors.felt, borderRadius: 12, width: 48, paddingVertical: 14, alignItems: 'center' },
  toast: {
    position: 'absolute', top: 60, alignSelf: 'center', maxWidth: '85%',
    backgroundColor: '#000c', borderRadius: 12, paddingHorizontal: 14, paddingVertical: 10,
  },
  toastText: { color: colors.text, textAlign: 'center' },
});
