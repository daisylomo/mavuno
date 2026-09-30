import { ReactNode, useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, AppState, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect, useRouter } from 'expo-router';
import { AppUser, userService } from '@/services/user-service';
import { instant } from '@/services/social-contracts';

export const errorText = (error: unknown) => error instanceof Error ? error.message : 'Something went wrong. Please retry.';
export const dateText = (date: string) => new Date(instant(date)).toLocaleString();
export const money = (amount: string, currency = 'KES') => `${currency} ${Number(amount).toLocaleString('en-KE', { maximumFractionDigits: 2 })}`;

/** Refresh only while this route and the app are active; stale requests cannot replace current state. */
export function useLiveData<T>(loader: () => Promise<T>, pollMs = 0) {
  const [value, setValue] = useState<T>();
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const generation = useRef(0);
  const active = useRef(false);
  const pending = useRef<number | null>(null);
  useEffect(() => { setValue(undefined); setError(''); setLoading(true); }, [loader]);
  const refresh = useCallback(async () => {
    if (!active.current || pending.current === generation.current) return;
    const current = generation.current;
    pending.current = current;
    setLoading(true);
    try {
      const result = await loader();
      if (active.current && current === generation.current) { setValue(result); setError(''); }
    } catch (reason) {
      if (active.current && current === generation.current) setError(errorText(reason));
    } finally {
      if (pending.current === current) pending.current = null;
      if (active.current && current === generation.current) setLoading(false);
    }
  }, [loader]);
  useFocusEffect(useCallback(() => {
    generation.current += 1;
    active.current = true;
    void refresh();
    const subscription = AppState.addEventListener('change', state => {
      active.current = state === 'active';
      generation.current += 1;
      if (active.current) void refresh();
    });
    const timer = pollMs ? setInterval(() => { if (active.current) void refresh(); }, pollMs) : null;
    return () => { active.current = false; generation.current += 1; subscription.remove(); if (timer) clearInterval(timer); };
  }, [refresh, pollMs]));
  return { value, error, loading, refresh };
}

const loadCurrentUser = () => userService.getCurrentUser();
export function useMarketplaceUser() { return useLiveData<AppUser | null>(loadCurrentUser); }

export function Screen({ title, children, scroll = true }: { title: string; children: ReactNode; scroll?: boolean }) {
  const router = useRouter();
  return <SafeAreaView style={ui.screen}>
    <View style={ui.header}>
      <Pressable accessibilityRole="button" accessibilityLabel="Back" onPress={() => router.canGoBack() ? router.back() : router.replace('/')} style={ui.back}><Text style={ui.headerText}>←</Text></Pressable>
      <Text style={ui.headerTitle}>{title}</Text>
    </View>
    <KeyboardAvoidingView style={ui.fill} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      {scroll ? <ScrollView contentContainerStyle={ui.content} keyboardShouldPersistTaps="handled">{children}</ScrollView> : <View style={ui.fill}>{children}</View>}
    </KeyboardAvoidingView>
  </SafeAreaView>;
}

export function Button({ title, onPress, disabled = false, secondary = false }: { title: string; onPress: () => void; disabled?: boolean; secondary?: boolean }) {
  return <Pressable accessibilityRole="button" accessibilityState={{ disabled }} disabled={disabled} onPress={onPress}
    style={[ui.button, secondary && ui.secondary, disabled && ui.disabled]}><Text style={[ui.buttonText, secondary && ui.secondaryText]}>{title}</Text></Pressable>;
}

export function Feedback({ loading, error, retry }: { loading?: boolean; error?: string; retry: () => void }) {
  return <>{loading && <ActivityIndicator accessibilityLabel="Refreshing" color="#216647" />}
    {!!error && <View style={ui.card}><Text accessibilityRole="alert" style={ui.error}>{error}</Text><Button title="Retry" onPress={retry} secondary /></View>}</>;
}

export function Field({ label, value, onChangeText, numeric = false, multiline = false, maxLength }: {
  label: string; value: string; onChangeText: (value: string) => void; numeric?: boolean; multiline?: boolean; maxLength?: number;
}) {
  return <View style={ui.field}><Text style={ui.label}>{label}</Text><TextInput accessibilityLabel={label} style={[ui.input, multiline && ui.multiline]}
    value={value} onChangeText={onChangeText} keyboardType={numeric ? 'decimal-pad' : 'default'} multiline={multiline} maxLength={maxLength} /></View>;
}

export const ui = StyleSheet.create({
  screen: { flex: 1, backgroundColor: '#F5F8F6' }, fill: { flex: 1 },
  header: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: 12, backgroundColor: '#216647' },
  headerText: { color: 'white', fontSize: 26 }, headerTitle: { color: 'white', fontSize: 20, fontWeight: '700', flex: 1 }, back: { padding: 8 },
  content: { padding: 18, gap: 16, width: '100%', maxWidth: 800, alignSelf: 'center', paddingBottom: 40 },
  card: { padding: 16, gap: 10, borderRadius: 14, backgroundColor: 'white', borderWidth: 1, borderColor: '#D9E6DE' },
  title: { fontSize: 20, fontWeight: '700', color: '#193A2B' }, text: { fontSize: 16, lineHeight: 24, color: '#253B30' },
  muted: { fontSize: 14, lineHeight: 21, color: '#53665C' }, error: { color: '#A51D27', fontSize: 15 },
  row: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 10 },
  button: { padding: 14, borderRadius: 10, backgroundColor: '#216647', alignItems: 'center', minHeight: 48 },
  buttonText: { color: 'white', fontWeight: '700', fontSize: 15 }, secondary: { backgroundColor: '#E5F1E9' }, secondaryText: { color: '#216647' }, disabled: { opacity: 0.5 },
  field: { gap: 8 }, label: { color: '#253B30', fontSize: 15, fontWeight: '600' }, input: { backgroundColor: 'white', borderColor: '#BDCEC3', borderWidth: 1, borderRadius: 10, padding: 12, color: '#172F23', fontSize: 16, minHeight: 48 },
  multiline: { minHeight: 100, textAlignVertical: 'top' }, badge: { color: '#216647', fontSize: 14, fontWeight: '700' },
});
