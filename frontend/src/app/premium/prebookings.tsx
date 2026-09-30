import { useState } from 'react';
import { Text, View } from 'react-native';
import { Button, dateText, errorText, Feedback, money, Screen, ui, useLiveData, useMarketplaceUser } from '@/components/marketplace-screen';
import { socialApi } from '@/services/social-api';
import { liveRequest } from '@/services/live-api';
import { bookingActions, Prebooking } from '@/services/social-contracts';

const loadBookings = async () => {
  const [bookings, products] = await Promise.all([socialApi.bookings(), liveRequest<Array<{ id: string; name: string }>>('/catalog/products')]);
  return { bookings, products };
};
const actionLabels = { accepted: 'Accept request', rejected: 'Decline request', cancelled: 'Cancel request', fulfilled: 'Mark fulfilled' };
export default function HarvestRequests() {
  const user = useMarketplaceUser();
  const requests = useLiveData(loadBookings, 15000);
  const [confirm, setConfirm] = useState<{ booking: Prebooking; status: keyof typeof actionLabels } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function transition() {
    if (!confirm || busy) return;
    setBusy(true); setError('');
    try { await socialApi.transitionBooking(confirm.booking, confirm.status); setConfirm(null); }
    catch (reason) { setError(errorText(reason)); setConfirm(null); }
    finally { await requests.refresh(); setBusy(false); }
  }
  return <Screen title="Harvest requests">
    <Text style={ui.text}>{user.value?.role === 'farmer' ? 'Review future harvest requests from buyers.' : 'Request a future harvest from a produce listing, then follow the farmer’s response here.'}</Text>
    <Text style={ui.muted}>Harvest requests do not charge you or reserve current stock. Arrange availability and handover with the farmer.</Text>
    <Button title="Refresh requests" onPress={() => void requests.refresh()} disabled={requests.loading || busy} secondary />
    <Feedback loading={!requests.value && requests.loading} error={requests.error || user.error} retry={() => { void user.refresh(); void requests.refresh(); }} />
    {!!error && <Text accessibilityRole="alert" style={ui.error}>{error}</Text>}
    {confirm && <View style={ui.card}><Text style={ui.title}>{actionLabels[confirm.status]}?</Text>
      <Text style={ui.text}>{confirm.status === 'fulfilled' ? 'Confirm this harvest request has already been fulfilled.' : `Confirm this change to request ${confirm.booking.id.slice(0, 8)}.`}</Text>
      <Button title="Confirm change" onPress={() => void transition()} disabled={busy} /><Button title="Keep current status" onPress={() => setConfirm(null)} disabled={busy} secondary /></View>}
    {requests.value?.bookings.length === 0 && <Text style={ui.muted}>No harvest requests yet.</Text>}
    {requests.value?.bookings.map(booking => <View key={booking.id} style={ui.card}>
      <Text style={ui.title}>{requests.value?.products.find(product => product.id === booking.product_id)?.name ?? 'Produce'} · {booking.quantity} {booking.quantity_unit}</Text>
      <Text style={ui.badge}>{booking.status.replace(/_/g, ' ')}</Text>
      <Text style={ui.muted}>Request {booking.id.slice(0, 8)}</Text>
      <Text style={ui.text}>{dateText(booking.window_start)} to {dateText(booking.window_end)}</Text>
      {booking.target_price !== null && <Text style={ui.text}>Proposed price: {money(booking.target_price, booking.currency)} / {booking.quantity_unit}</Text>}
      {!!booking.notes && <Text style={ui.text}>{booking.notes}</Text>}
      <View style={ui.row}>{bookingActions(booking, user.value?.id ?? '').map(status => <Button key={status} title={actionLabels[status]} onPress={() => setConfirm({ booking, status })} disabled={busy} secondary={status !== 'accepted'} />)}</View>
    </View>)}
  </Screen>;
}
