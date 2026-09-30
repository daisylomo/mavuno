import AsyncStorage from '@react-native-async-storage/async-storage';
import { randomUUID } from 'expo-crypto';
import { useRouter } from 'expo-router';
import { useRef, useState } from 'react';
import { Text, View } from 'react-native';
import { Button, dateText, errorText, Feedback, money, Screen, ui, useLiveData, useMarketplaceUser } from '@/components/marketplace-screen';
import { socialApi } from '@/services/social-api';
import { hasFeature, Plan } from '@/services/social-contracts';

const loadMembership = async () => {
  const [plans, subscriptions, availability] = await Promise.all([socialApi.plans(), socialApi.subscriptions(), socialApi.availability()]);
  return { plans, subscriptions, availability };
};
const featureNames: Record<string, string> = { prebooking: 'Request future harvests', insights: 'Farm sales insights' };

export default function Membership() {
  const router = useRouter();
  const user = useMarketplaceUser();
  const membership = useLiveData(loadMembership, 15000);
  const [confirm, setConfirm] = useState<Plan | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const submitting = useRef(false);
  const audience = user.value?.role === 'farmer' ? 'farmer' : 'buyer';
  const data = membership.value;
  async function subscribe(plan: Plan) {
    if (!user.value || submitting.current || !data?.availability.subscriptions_available) return;
    submitting.current = true; setBusy(true); setError(''); setNotice('');
    try {
      const keyName = `@mavuno_subscription_request:${user.value.id}:${plan.id}`;
      const previous = data.subscriptions.find(subscription => subscription.plan_id === plan.id);
      let key = !previous || previous.status === 'pending' ? await AsyncStorage.getItem(keyName) : null;
      // Never invent a new key for an existing pending request created on another device.
      if (previous?.status === 'pending' && !key) throw new Error('This request was started on another device. Refresh its status or use the account reference with your provider.');
      key ??= randomUUID();
      await AsyncStorage.setItem(keyName, key);
      const subscription = await socialApi.subscribe(plan.id, key);
      setConfirm(null);
      setNotice(`Request ${subscription.account_reference} was submitted. Its current status appears below. Benefits unlock after provider verification.`);
      await membership.refresh();
    } catch (reason) { setError(errorText(reason)); await membership.refresh(); }
    finally { submitting.current = false; setBusy(false); }
  }
  return <Screen title="Premium membership">
    <Text style={ui.text}>Choose benefits for your account and track your membership here.</Text>
    <View style={ui.row}><Button title="Harvest requests" onPress={() => router.push('/premium/prebookings')} secondary />
      {audience === 'farmer' && <Button title="Farm insights" onPress={() => router.push('/premium/insights')} secondary />}</View>
    <Button title="Refresh membership" onPress={() => void membership.refresh()} disabled={membership.loading || busy} secondary />
    <Button title="Upgrade with RevenueCat" onPress={() => router.push('/premium/upgrade')} />
    <Feedback loading={!data && membership.loading} error={membership.error || user.error} retry={() => { void user.refresh(); void membership.refresh(); }} />
    {!!error && <Text accessibilityRole="alert" style={ui.error}>{error}</Text>}
    {!!notice && <Text style={ui.badge}>{notice}</Text>}
    {data && !data.availability.subscriptions_available && <View style={ui.card}><Text style={ui.title}>New subscriptions unavailable</Text><Text style={ui.text}>You can still view existing memberships and harvest requests. Try again later to purchase a plan.</Text></View>}
    {confirm && <View style={ui.card}>
      <Text style={ui.title}>Confirm {confirm.name}</Text><Text style={ui.text}>{money(confirm.price_amount, confirm.currency)} per {confirm.billing_interval}.</Text>
      <Text style={ui.muted}>This sends a subscription request to the membership provider. Access starts only after the provider verifies the subscription. Billing and renewal changes are handled by your provider.</Text>
      <Button title="Confirm subscription request" onPress={() => void subscribe(confirm)} disabled={busy} />
      <Button title="Go back" onPress={() => setConfirm(null)} disabled={busy} secondary />
    </View>}
    <Text style={ui.title}>Plans for you</Text>
    {data?.plans.filter(plan => plan.active && plan.audience === audience).length === 0 && <Text style={ui.muted}>No plans are offered for your account yet.</Text>}
    {data?.plans.filter(plan => plan.active && plan.audience === audience).map(plan => {
      const current = data.subscriptions.find(subscription => subscription.plan_id === plan.id);
      const active = hasFeature(data.subscriptions, [plan], plan.features[0] ?? '');
      return <View key={plan.id} style={ui.card}>
        <Text style={ui.title}>{plan.name}</Text><Text style={ui.text}>{money(plan.price_amount, plan.currency)} / {plan.billing_interval}</Text>
        {plan.features.map(feature => <Text key={feature} style={ui.muted}>• {featureNames[feature] ?? feature}</Text>)}
        {active ? <Text style={ui.badge}>Verified membership active</Text> : <Button title={current?.status === 'pending' ? 'Retry pending request' : 'Choose this plan'}
          onPress={() => { setError(''); setConfirm(plan); }} disabled={busy || !data.availability.subscriptions_available || !user.value} />}
      </View>;
    })}
    <Text style={ui.title}>Your subscription history</Text>
    {data?.subscriptions.length === 0 && <Text style={ui.muted}>You have no subscriptions.</Text>}
    {data?.subscriptions.map(subscription => <View key={subscription.id} style={ui.card}>
      <Text style={ui.title}>{data.plans.find(plan => plan.id === subscription.plan_id)?.name ?? 'Membership'}</Text>
      <Text style={ui.badge}>{subscription.status.replace(/_/g, ' ')}</Text>
      <Text selectable style={ui.muted}>Provider account reference: {subscription.account_reference}</Text>
      {!!subscription.current_period_end && <Text style={ui.text}>Period ends: {dateText(subscription.current_period_end)}</Text>}
      {subscription.status === 'active' && !subscription.verified_at && <Text style={ui.muted}>Awaiting verification. Benefits are not unlocked yet.</Text>}
    </View>)}
    <Text style={ui.muted}>Use your account reference when asking your provider about billing, renewal or cancellation. Mavuno displays the status confirmed by that provider.</Text>
  </Screen>;
}
