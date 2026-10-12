import { Pressable, ScrollView, Text } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRoom } from '../useRoom';
import { colors } from '../theme';

export default function TableScreen({ code, name, onExit }: { code: string; name: string; onExit: () => void }) {
  const room = useRoom(code, name);
  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.feltDark, padding: 16 }}>
      <Text style={{ color: colors.text, fontSize: 28, fontWeight: '800' }}>{code}</Text>
      <Text style={{ color: colors.muted }}>{room.fatal ?? room.status}</Text>
      <ScrollView>
        <Text style={{ color: colors.text, fontFamily: 'Courier' }}>
          {JSON.stringify({ players: room.players, piles: room.view?.piles.length, hand: room.view?.hand }, null, 2)}
        </Text>
      </ScrollView>
      <Pressable onPress={() => { room.leave(); onExit(); }}>
        <Text style={{ color: colors.accent, fontSize: 18 }}>Leave</Text>
      </Pressable>
    </SafeAreaView>
  );
}
