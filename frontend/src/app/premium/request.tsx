import { useLocalSearchParams, useRouter } from 'expo-router';
import { useCallback, useRef, useState } from 'react';
import { Text, View } from 'react-native';
import { Button, errorText, Feedback, Field, Screen, ui, useLiveData } from '@/components/marketplace-screen';
import { socialApi } from '@/services/social-api';
import { harvestWindow, hasEntitlement } from '@/services/social-contracts';
import RoleGate from '@/components/role-gate';

export default function RequestHarvest() {
  const { listingId } = useLocalSearchParams<{ listingId: string }>();
  const router = useRouter();
  const load = useCallback(async () => {
    const [listing, entitlements] = await Promise.all([socialApi.listing(listingId), socialApi.entitlements()]);
    return { listing, entitled: hasEntitlement(entitlements, 'prebooking') };
  }, [listingId]);
  const data = useLiveData(load);
  const [quantity, setQuantity] = useState('1');
  const [price, setPrice] = useState('');
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [notes, setNotes] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const submitted = useRef(false);
  async function submit() {
    if (!data.value?.entitled || submitted.current) return;
    submitted.current = true; setBusy(true); setError('');
    try {
      if (!/^\d+(\.\d{1,3})?$/.test(quantity) || !Number.isFinite(Number(quantity)) || Number(quantity) <= 0) throw new Error('Enter a positive quantity with at most three decimal places.');
      if (price && (!/^\d+(\.\d{1,4})?$/.test(price) || !Number.isFinite(Number(price)))) throw new Error('Enter a valid proposed price or leave it empty.');
      const listing = data.value.listing;
      await socialApi.createBooking({ listing_id: listing.id, product_id: listing.product_id, farmer_id: listing.farmer_id,
        quantity, quantity_unit: listing.quantity_unit, target_price: price || null, notes: notes.trim() || null, ...harvestWindow(start, end) });
      router.replace('/premium/prebookings');
    } catch (reason) { setError(errorText(reason)); submitted.current = false; }
    finally { setBusy(false); }
  }
  return <RoleGate allowedRoles={['customer']}><Screen title="Request a future harvest">
    <Feedback loading={!data.value && data.loading} error={data.error} retry={() => void data.refresh()} />
    {!!error && <Text accessibilityRole="alert" style={ui.error}>{error}</Text>}
    {data.value && <>
      <Text style={ui.title}>{data.value.listing.title}</Text>
      {!!data.value.listing.farmer && <Text style={ui.text}>Farmer: {data.value.listing.farmer.display_name}</Text>}
      {!data.value.entitled ? <View style={ui.card}><Text style={ui.badge}>Premium feature</Text><Text style={ui.text}>Requesting future harvests is part of Mavuno Premium.</Text><Button title="Upgrade to Premium" onPress={() => router.push('/premium/upgrade')} /></View> : <>
        <Text style={ui.muted}>Dates use Kenya time. This request does not reserve stock or collect a payment.</Text>
        <Field label={`Quantity (${data.value.listing.quantity_unit})`} value={quantity} onChangeText={setQuantity} numeric />
        <Field label={`Proposed KES price per ${data.value.listing.quantity_unit} (optional)`} value={price} onChangeText={setPrice} numeric />
        <Field label="Harvest window start (YYYY-MM-DD)" value={start} onChangeText={setStart} maxLength={10} />
        <Field label="Harvest window end (YYYY-MM-DD)" value={end} onChangeText={setEnd} maxLength={10} />
        <Field label="Notes for the farmer (optional)" value={notes} onChangeText={setNotes} maxLength={500} multiline />
        <Button title={busy ? 'Sending request…' : 'Send harvest request'} onPress={() => void submit()} disabled={busy} />
      </>}
    </>}
  </Screen></RoleGate>;
}
