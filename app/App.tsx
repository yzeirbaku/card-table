import { useState } from 'react';
import { StatusBar } from 'expo-status-bar';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import HomeScreen from './src/screens/HomeScreen';
import TableScreen from './src/screens/TableScreen';

type Seat = { code: string; name: string };

export default function App() {
  const [seat, setSeat] = useState<Seat | null>(null);
  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <StatusBar style="light" />
        {seat ? (
          <TableScreen code={seat.code} name={seat.name} onExit={() => setSeat(null)} />
        ) : (
          <HomeScreen onEnter={(code, name) => setSeat({ code, name })} />
        )}
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
