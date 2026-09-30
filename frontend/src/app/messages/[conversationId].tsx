import AsyncStorage from '@react-native-async-storage/async-storage';
import { randomUUID } from 'expo-crypto';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useCallback, useEffect, useRef, useState } from 'react';
import { FlatList, StyleSheet, Text, TextInput, View } from 'react-native';
import { Button, dateText, errorText, Feedback, Screen, ui, useLiveData, useMarketplaceUser } from '@/components/marketplace-screen';
import { socialApi } from '@/services/social-api';
import { mergeMessages, Message, uuid } from '@/services/social-contracts';

type Draft = { id: string; body: string };
export default function ConversationThread() {
  const { conversationId } = useLocalSearchParams<{ conversationId: string }>();
  const router = useRouter();
  const user = useMarketplaceUser();
  const load = useCallback(async () => ({ id: conversationId, ...await socialApi.messages(conversationId) }), [conversationId]);
  const page = useLiveData(load, 10000);
  const [messages, setMessages] = useState<Message[]>([]);
  const [olderCursor, setOlderCursor] = useState<string | null>(null);
  const [body, setBody] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [draftReady, setDraftReady] = useState(false);
  const [moreBusy, setMoreBusy] = useState(false);
  const sending = useRef<string | null>(null);
  const draft = useRef<Draft | null>(null);
  const loadedHistory = useRef(false);
  const readMarker = useRef<string | null>(null);
  const currentRoute = useRef(conversationId);
  currentRoute.current = conversationId;
  const draftKey = user.value?.id ? `@mavuno_message_draft:${user.value.id}:${conversationId}` : null;

  useEffect(() => {
    setMessages([]); setBody(''); setOlderCursor(null); setError(''); setBusy(false); setMoreBusy(false);
    loadedHistory.current = false; readMarker.current = null; draft.current = null;
  }, [conversationId]);
  useEffect(() => {
    let active = true;
    setDraftReady(false);
    if (!draftKey) return;
    AsyncStorage.getItem(draftKey).then(raw => {
      if (!active || !raw) return;
      try {
        const stored: unknown = JSON.parse(raw);
        if (stored && typeof stored === 'object' && 'id' in stored && 'body' in stored &&
          typeof stored.id === 'string' && typeof stored.body === 'string') {
          uuid(stored.id);
          if (stored.body.length > 4000) return;
          draft.current = { id: stored.id, body: stored.body }; setBody(stored.body);
        }
      } catch { /* A corrupt local draft must not stop an authenticated conversation. */ }
    }).catch(reason => { if (active) setError(errorText(reason)); }).finally(() => { if (active) setDraftReady(true); });
    return () => { active = false; };
  }, [draftKey]);
  useEffect(() => {
    if (!page.value || page.value.id !== conversationId) return;
    const current = page.value.items.filter(message => message.conversation_id === conversationId);
    setMessages(existing => mergeMessages(existing, current));
    if (!loadedHistory.current) setOlderCursor(page.value.next_cursor);
    const latest = mergeMessages([], current).at(-1);
    if (latest && latest.id !== readMarker.current) {
      socialApi.read(conversationId, latest.id).then(() => {
        if (currentRoute.current === conversationId) readMarker.current = latest.id;
      }).catch(reason => { if (currentRoute.current === conversationId) setError(errorText(reason)); });
    }
  }, [page.value, conversationId]);

  async function send() {
    if (sending.current === conversationId || !draftKey || !draftReady || !body.trim()) return;
    sending.current = conversationId; setBusy(true); setError('');
    const route = conversationId;
    const normalized = body.trim();
    const pending = draft.current?.body === normalized ? draft.current : { id: randomUUID(), body: normalized };
    draft.current = pending;
    try {
      // Preserve the message id before transmission so a lost acknowledgement/restart can be retried safely.
      await AsyncStorage.setItem(draftKey, JSON.stringify(pending));
      const sent = await socialApi.send(route, pending.id, pending.body);
      if (currentRoute.current !== route) return;
      setMessages(existing => mergeMessages(existing, [sent])); setBody(''); draft.current = null;
      await AsyncStorage.removeItem(draftKey);
      await page.refresh();
    } catch (reason) { if (currentRoute.current === route) setError(errorText(reason)); }
    finally { if (sending.current === route) sending.current = null; if (currentRoute.current === route) setBusy(false); }
  }
  async function older() {
    if (!olderCursor || moreBusy) return;
    setMoreBusy(true); setError('');
    const route = conversationId;
    try {
      const previous = await socialApi.messages(route, olderCursor);
      if (currentRoute.current !== route) return;
      setMessages(existing => mergeMessages(existing, previous.items)); setOlderCursor(previous.next_cursor); loadedHistory.current = true;
    } catch (reason) { if (currentRoute.current === route) setError(errorText(reason)); }
    finally { if (currentRoute.current === route) setMoreBusy(false); }
  }
  return <Screen title="Conversation" scroll={false}>
    <View style={styles.toolbar}><Button title="Inbox" onPress={() => router.push('/messages')} secondary /><Button title="Refresh messages" disabled={page.loading} onPress={() => void page.refresh()} secondary /></View>
    <View style={styles.feedback}><Feedback loading={!page.value && page.loading} error={page.error || error} retry={() => { setError(''); void page.refresh(); }} /></View>
    <FlatList data={[...messages].reverse()} inverted keyExtractor={message => message.id} contentContainerStyle={styles.messages}
      ListEmptyComponent={!page.loading ? <Text style={ui.muted}>No messages yet. Say hello below.</Text> : null}
      ListFooterComponent={olderCursor ? <Button title="Load older messages" onPress={() => void older()} disabled={moreBusy} secondary /> : null}
      renderItem={({ item }) => <View style={[styles.bubble, item.sender_id === user.value?.id && styles.mine]}>
        <Text style={ui.badge}>{item.sender_id === user.value?.id ? 'You' : 'Other participant'}</Text>
        <Text selectable style={ui.text}>{item.body}</Text><Text style={ui.muted}>{dateText(item.created_at)}</Text>
      </View>} />
    <View style={styles.composer}>
      <TextInput accessibilityLabel="Message" placeholder="Write a message…" style={[ui.input, styles.messageInput]} value={body} onChangeText={setBody}
        maxLength={4000} multiline editable={draftReady && !busy} />
      <Text style={ui.muted}>{body.length}/4,000</Text>
      <Button title={busy ? 'Sending…' : 'Send message'} onPress={() => void send()} disabled={busy || !draftReady || !body.trim() || page.value?.id !== conversationId} />
      {!!error && <Text style={ui.muted}>Your message is kept here. Retry sending it when your connection returns.</Text>}
    </View>
  </Screen>;
}
const styles = StyleSheet.create({ toolbar: { padding: 12, flexDirection: 'row', gap: 10 }, feedback: { paddingHorizontal: 16 },
  messages: { padding: 16, gap: 12 }, bubble: { padding: 12, gap: 6, borderRadius: 12, backgroundColor: 'white', maxWidth: '90%', alignSelf: 'flex-start' },
  mine: { backgroundColor: '#DCEEE1', alignSelf: 'flex-end' }, composer: { padding: 14, gap: 8, borderTopWidth: 1, borderColor: '#D9E6DE' }, messageInput: { maxHeight: 130, minHeight: 65 } });
