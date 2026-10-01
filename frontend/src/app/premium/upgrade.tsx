import { useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Text, View } from 'react-native';
import { Button, errorText, Feedback, Screen, ui, useLiveData, useMarketplaceUser } from '@/components/marketplace-screen';
import { useRevenueCat } from '@/providers/revenuecat-provider';
import { socialApi } from '@/services/social-api';
import { refreshPremiumEntitlements } from '@/services/premium-refresh';
import { Entitlements } from '@/services/social-contracts';

const loadEntitlements = () => refreshPremiumEntitlements(socialApi);
const benefits = {
  customer: ['Request future harvests directly from farmers', 'Agree quantities, dates and a proposed price before the harvest'],
  farmer: ['Farm sales insights: active listings, stock and completed orders', 'Gross sales from completed orders at a glance'],
};

/** Standard accounts land here. Buying goes through the store (RevenueCat); unlocking is the backend's call. */
export default function Upgrade() {
  const router = useRouter();
  const user = useMarketplaceUser();
  const entitlements = useLiveData(loadEntitlements);
  const store = useRevenueCat();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const premium = entitlements.value?.premium;
  useEffect(() => { if (premium) router.replace('/premium'); }, [premium, router]);

  async function run(action: () => Promise<Entitlements | null>, notUnlocked: string) {
    if (busy) return;
    setBusy(true); setError(''); setNotice('');
    try {
      const result = await action();
      if (result?.premium) { router.replace('/premium'); return; }
      if (result) setNotice(notUnlocked);
      await entitlements.refresh();
    } catch (reason) { setError(errorText(reason)); }
    finally { setBusy(false); }
  }

  const role = user.value?.role === 'farmer' ? 'farmer' : 'customer';
  // The backend must accept store purchases and RevenueCat must have loaded something to sell.
  const canRestore = !!entitlements.value?.purchases_available && store.ready;
  const available = canRestore && store.currentOffering !== null;
  return <Screen title="Mavuno Premium">
    <Feedback loading={!entitlements.value && entitlements.loading} error={entitlements.error || user.error}
      retry={() => { void user.refresh(); void entitlements.refresh(); }} />
    {entitlements.value && !premium && <>
      <View style={ui.card}>
        <Text style={ui.badge}>Your plan: Standard</Text>
        <Text style={ui.title}>Upgrade to Premium</Text>
        {benefits[role].map(benefit => <Text key={benefit} style={ui.text}>• {benefit}</Text>)}
        <Text style={ui.muted}>Payment, renewal and cancellation are handled by your app store. Premium unlocks as soon as Mavuno confirms the purchase.</Text>
      </View>
      {!store.ready && <ActivityIndicator accessibilityLabel="Loading plans" color="#216647" />}
      {store.ready && !available && <View style={ui.card}><Text style={ui.title}>Premium purchases unavailable</Text>
        <Text style={ui.text}>{store.error ?? 'Premium cannot be bought right now. Try again later.'}</Text></View>}
      {!!error && <Text accessibilityRole="alert" style={ui.error}>{error}</Text>}
      {!!notice && <Text style={ui.badge}>{notice}</Text>}
      <Button title={busy ? 'Please wait…' : 'See Premium plans'} disabled={busy || !available}
        onPress={() => void run(store.presentPaywall, 'Your purchase is being confirmed. Refresh in a moment.')} />
      <Button title="Restore purchases" secondary disabled={busy || !canRestore}
        onPress={() => void run(store.restore, 'No Premium purchase was found for this store account.')} />
      <Button title="Refresh" secondary disabled={busy || entitlements.loading} onPress={() => void entitlements.refresh()} />
      {/* Answering harvest requests is free for farmers, and buyers keep sight of past requests. */}
      <Button title="Harvest requests" secondary onPress={() => router.push('/premium/prebookings')} />
    </>}
  </Screen>;
}
