import { useRouter } from 'expo-router';
import { Text, View } from 'react-native';
import { Button, Feedback, money, Screen, ui, useLiveData } from '@/components/marketplace-screen';
import { socialApi } from '@/services/social-api';
import { hasFeature } from '@/services/social-contracts';
import RoleGate from '@/components/role-gate';

const loadInsights = async () => {
  const [plans, subscriptions] = await Promise.all([socialApi.plans(), socialApi.subscriptions()]);
  const entitled = hasFeature(subscriptions, plans, 'insights');
  return { entitled, insights: entitled ? await socialApi.insights() : null };
};
export default function FarmInsights() {
  const router = useRouter();
  const data = useLiveData(loadInsights);
  return <RoleGate allowedRoles={['farmer']}><Screen title="Farm insights">
    <Feedback loading={!data.value && data.loading} error={data.error} retry={() => void data.refresh()} />
    <Button title="Refresh insights" onPress={() => void data.refresh()} disabled={data.loading} secondary />
    {data.value && !data.value.entitled && <View style={ui.card}><Text style={ui.text}>Farm insights require a verified membership with this benefit.</Text><Button title="View premium membership" onPress={() => router.push('/premium')} /></View>}
    {data.value?.insights && <>
      <View style={ui.card}><Text style={ui.title}>{data.value.insights.active_listings}</Text><Text style={ui.text}>Active produce listings</Text></View>
      <View style={ui.card}><Text style={ui.title}>{data.value.insights.completed_order_lines}</Text><Text style={ui.text}>Completed order items</Text></View>
      <View style={ui.card}><Text style={ui.title}>{money(data.value.insights.gross_sales)}</Text><Text style={ui.text}>Gross sales from completed items</Text><Text style={ui.muted}>Gross sales are not net profit or a payout balance.</Text></View>
    </>}
  </Screen></RoleGate>;
}
