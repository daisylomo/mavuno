import { Redirect, useRouter } from 'expo-router';
import { useState } from 'react';
import { Text, View } from 'react-native';
import { Button, dateText, errorText, Feedback, Screen, ui, useLiveData, useMarketplaceUser } from '@/components/marketplace-screen';
import { useRevenueCat } from '@/providers/revenuecat-provider';
import { socialApi } from '@/services/social-api';
import { refreshPremiumEntitlements } from '@/services/premium-refresh';

const loadEntitlements = () => refreshPremiumEntitlements(socialApi);

/** The Premium area. Only accounts the backend confirms as Premium see it; others go to the upgrade screen. */
export default function PremiumHome() {
  const router = useRouter();
  const user = useMarketplaceUser();
  const entitlements = useLiveData(loadEntitlements, 60000);
  const { presentCustomerCenter } = useRevenueCat();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const value = entitlements.value;
  if (value && !value.premium) return <Redirect href="/premium/upgrade" />;

  async function manage() {
    if (busy) return;
    setBusy(true); setError('');
    try {
      const result = await presentCustomerCenter();
      if (result && !result.premium) { router.replace('/premium/upgrade'); return; }
      await entitlements.refresh();
    } catch (reason) { setError(errorText(reason)); }
    finally { setBusy(false); }
  }

  return <Screen title="Mavuno Premium">
    <Feedback loading={!value && entitlements.loading} error={entitlements.error || user.error}
      retry={() => { void user.refresh(); void entitlements.refresh(); }} />
    {!!error && <Text accessibilityRole="alert" style={ui.error}>{error}</Text>}
    {value?.premium && <>
      <View style={ui.card}>
        <Text style={ui.badge}>Your plan: Premium</Text>
        <Text style={ui.text}>{value.expires_at ? `Current period ends ${dateText(value.expires_at)}.` : 'Your Premium access has no end date.'}</Text>
      </View>
      <View style={ui.row}>
        <Button title="Harvest requests" onPress={() => router.push('/premium/prebookings')} secondary />
        {user.value?.role === 'farmer' && <Button title="Farm insights" onPress={() => router.push('/premium/insights')} secondary />}
      </View>
      {value.provider === 'revenuecat' && <Button title="Manage subscription" onPress={() => void manage()} disabled={busy} secondary />}
      <Button title="Refresh" onPress={() => void entitlements.refresh()} disabled={entitlements.loading || busy} secondary />
    </>}
  </Screen>;
}
