import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { httpUrl } from '../config';
import { loadName, saveName } from '../seat';
import { colors } from '../theme';

export default function HomeScreen({ onEnter }: { onEnter: (code: string, name: string) => void }) {
  const [name, setName] = useState('');
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void loadName().then((n) => n && setName(n));
  }, []);

  const trimmed = name.trim();
  const nameOk = trimmed.length >= 1 && trimmed.length <= 20;
  const codeOk = /^[A-Za-z]{4}$/.test(code);

  async function create() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(httpUrl('/rooms'), { method: 'POST' });
      if (!res.ok) throw new Error(String(res.status));
      const body = (await res.json()) as { code: string };
      await saveName(trimmed);
      onEnter(body.code, trimmed);
    } catch {
      setError("Couldn't reach the server. Is it running, and is your phone on the same Wi-Fi?");
    } finally {
      setBusy(false);
    }
  }

  async function join() {
    await saveName(trimmed);
    onEnter(code.toUpperCase(), trimmed);
  }

  return (
    <SafeAreaView style={styles.screen}>
      <Text style={styles.title}>Card Table</Text>
      <TextInput
        style={styles.input}
        placeholder="Your name"
        placeholderTextColor={colors.muted}
        value={name}
        onChangeText={setName}
        maxLength={20}
        autoCorrect={false}
      />
      <Pressable
        style={[styles.button, !(nameOk && !busy) && styles.disabled]}
        disabled={!nameOk || busy}
        onPress={create}
      >
        {busy ? <ActivityIndicator color={colors.feltDark} /> : <Text style={styles.buttonText}>Create room</Text>}
      </Pressable>
      <Text style={styles.or}>or join one</Text>
      <View style={styles.row}>
        <TextInput
          style={[styles.input, styles.codeInput]}
          placeholder="CODE"
          placeholderTextColor={colors.muted}
          value={code}
          onChangeText={(t) => setCode(t.toUpperCase())}
          maxLength={4}
          autoCapitalize="characters"
          autoCorrect={false}
        />
        <Pressable
          style={[styles.button, styles.joinButton, !(nameOk && codeOk) && styles.disabled]}
          disabled={!nameOk || !codeOk}
          onPress={join}
        >
          <Text style={styles.buttonText}>Join</Text>
        </Pressable>
      </View>
      {error && <Text style={styles.error}>{error}</Text>}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.feltDark, padding: 24, justifyContent: 'center', gap: 14 },
  title: { color: colors.text, fontSize: 36, fontWeight: '800', textAlign: 'center', marginBottom: 24 },
  input: {
    backgroundColor: colors.felt, color: colors.text, fontSize: 18,
    borderRadius: 12, paddingHorizontal: 16, paddingVertical: 14,
  },
  codeInput: { flex: 1, letterSpacing: 6, textAlign: 'center', fontWeight: '700' },
  button: { backgroundColor: colors.accent, borderRadius: 12, paddingVertical: 16, alignItems: 'center' },
  joinButton: { paddingHorizontal: 28 },
  buttonText: { color: colors.feltDark, fontSize: 18, fontWeight: '700' },
  disabled: { opacity: 0.4 },
  or: { color: colors.muted, textAlign: 'center', marginTop: 12 },
  row: { flexDirection: 'row', gap: 10 },
  error: { color: colors.danger, textAlign: 'center', marginTop: 8 },
});
