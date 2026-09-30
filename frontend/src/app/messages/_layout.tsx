import { Stack } from 'expo-router';
import RoleGate from '@/components/role-gate';
export default function MessagesLayout() {
  return <RoleGate allowedRoles={['customer', 'farmer']}><Stack screenOptions={{ headerShown: false }} /></RoleGate>;
}
