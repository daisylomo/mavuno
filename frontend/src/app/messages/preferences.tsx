import { useEffect, useState } from 'react';
import { Switch, Text, View } from 'react-native';
import { Button, errorText, Feedback, Screen, ui, useLiveData } from '@/components/marketplace-screen';
import { socialApi } from '@/services/social-api';

export default function NotificationPreferences() {
  const data = useLiveData(socialApi.preferences);
  const [messages, setMessages] = useState(true);
  const [orders, setOrders] = useState(true);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  useEffect(() => { if (data.value) { setMessages(data.value.messages_push); setOrders(data.value.orders_push); } }, [data.value]);
  async function save() {
    if (busy || !data.value) return;
    setBusy(true); setError(''); setNotice('');
    try { await socialApi.updatePreferences({ messages_push: messages, orders_push: orders }); setNotice('Preferences saved.'); }
    catch (reason) { setError(errorText(reason)); } finally { setBusy(false); }
  }
  return <Screen title="Notification preferences">
    <Text style={ui.text}>These preferences apply to push-enabled devices. In-app notifications remain available in your inbox.</Text>
    <Feedback loading={data.loading} error={data.error || error} retry={() => void data.refresh()} />
    <View style={ui.card}><Text style={ui.label}>Message push alerts</Text><Switch accessibilityLabel="Message push alerts" value={messages} onValueChange={setMessages} disabled={!data.value || busy} /></View>
    <View style={ui.card}><Text style={ui.label}>Order push alerts</Text><Switch accessibilityLabel="Order push alerts" value={orders} onValueChange={setOrders} disabled={!data.value || busy} /></View>
    {!!notice && <Text style={ui.badge}>{notice}</Text>}<Button title="Save preferences" onPress={() => void save()} disabled={busy || !data.value} />
  </Screen>;
}
