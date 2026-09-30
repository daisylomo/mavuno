import { useRouter } from 'expo-router';
import { View } from 'react-native';
import { isBackendConfigured } from '@/services/auth-api';
import { Button, ui } from './marketplace-screen';

export default function MarketplaceLinks() {
  const router = useRouter();
  if (!isBackendConfigured()) return null;
  return <View style={ui.row}>
    <Button title="Messages" onPress={() => router.push('/messages')} secondary />
    <Button title="Premium" onPress={() => router.push('/premium')} secondary />
    <Button title="Profile" onPress={() => router.push('/profile')} secondary />
  </View>;
}
