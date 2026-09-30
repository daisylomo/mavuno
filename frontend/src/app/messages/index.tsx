import { useState } from 'react';
import { Pressable, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import { Button, dateText, errorText, Feedback, Screen, ui, useLiveData, useMarketplaceUser } from '@/components/marketplace-screen';
import { socialApi } from '@/services/social-api';
import { Notification, uuid } from '@/services/social-contracts';

const loadInbox = async () => {
  const [conversations, notifications] = await Promise.all([socialApi.conversations(), socialApi.notifications()]);
  return { conversations, notifications };
};

export default function Inbox() {
  const router = useRouter();
  const inbox = useLiveData(loadInbox, 10000);
  const user = useMarketplaceUser();
  const [tab, setTab] = useState<'messages' | 'notifications'>('messages');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const unread = inbox.value?.notifications.filter(notification => !notification.read_at).length ?? 0;
  async function openNotification(notification: Notification, open: boolean) {
    if (busy) return;
    setBusy(true); setError('');
    try {
      if (!notification.read_at) await socialApi.readNotification(notification.id);
      await inbox.refresh();
      if (open && typeof notification.data.conversation_id === 'string') {
        router.push({ pathname: '/messages/[conversationId]', params: { conversationId: uuid(notification.data.conversation_id) } });
      } else if (open && notification.data.order_id) router.push(user.value?.role === 'farmer' ? '/farmer/orders' : '/customer');
    } catch (reason) { setError(errorText(reason)); } finally { setBusy(false); }
  }
  return <Screen title="Messages & notifications">
    <View style={ui.row}>
      <Button title="Conversations" onPress={() => setTab('messages')} secondary={tab !== 'messages'} />
      <Button title={`Notifications${unread ? ` (${unread} unread)` : ''}`} onPress={() => setTab('notifications')} secondary={tab !== 'notifications'} />
    </View>
    <Button title="Refresh inbox" onPress={() => void inbox.refresh()} disabled={inbox.loading} secondary />
    <Button title="Notification preferences" onPress={() => router.push('/messages/preferences')} secondary />
    <Feedback loading={!inbox.value && inbox.loading} error={inbox.error || error} retry={() => { setError(''); void inbox.refresh(); }} />
    {tab === 'messages' ? <>
      <Text style={ui.muted}>Start a conversation from a produce listing or an order. Keep payment requests and personal details within Mavuno.</Text>
      {inbox.value?.conversations.length === 0 && <Text style={ui.text}>No conversations yet.</Text>}
      {inbox.value?.conversations.map(conversation => <Pressable accessibilityRole="button" key={conversation.id} style={ui.card}
        onPress={() => router.push({ pathname: '/messages/[conversationId]', params: { conversationId: conversation.id } })}>
        <Text style={ui.title}>{conversation.counterpart_name}</Text>
        <Text style={ui.muted}>{conversation.scope_label}</Text>
        <Text numberOfLines={2} style={ui.text}>{conversation.last_message_preview ?? 'No messages yet. Open to say hello.'}</Text>
        {!!conversation.unread_count && <Text style={ui.badge}>{conversation.unread_count} unread</Text>}
        {!!conversation.last_message_at && <Text style={ui.muted}>{dateText(conversation.last_message_at)}</Text>}
      </Pressable>)}
    </> : <>
      {inbox.value?.notifications.length === 0 && <Text style={ui.text}>No notifications yet.</Text>}
      {inbox.value?.notifications.map(notification => <View key={notification.id} style={ui.card}>
        <Text style={ui.title}>{notification.title}{!notification.read_at ? ' · Unread' : ''}</Text>
        <Text style={ui.text}>{notification.body}</Text><Text style={ui.muted}>{dateText(notification.created_at)}</Text>
        {!!(notification.data.conversation_id || notification.data.order_id) && <Button title="Open" onPress={() => void openNotification(notification, true)} disabled={busy} />}
        {!notification.read_at && <Button title="Mark as read" onPress={() => void openNotification(notification, false)} disabled={busy} secondary />}
      </View>)}
    </>}
  </Screen>;
}
