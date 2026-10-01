import { Href, Stack, useRouter } from 'expo-router';
import { Pressable, Text, View } from 'react-native';
import React from 'react';
import { Colors } from '../../constants/theme';
import { userService } from '../../services/user-service';
import RoleGate from '../../components/role-gate';

export default function FarmerLayout() {
  const router = useRouter();

  const handleLogout = async () => {
    await userService.logout();
    router.replace('/auth/login' as Href);
  };

  const navigateBack = () => {
    if (router.canGoBack()) {
      router.back();
    } else {
      router.replace('/farmer' as Href);
    }
  };

  return <RoleGate allowedRoles={['farmer']}>
    <Stack
      screenOptions={{
        headerStyle: { backgroundColor: Colors.brandGreen },
        headerTintColor: '#fff',
        headerTitleStyle: { fontWeight: 'bold' },
      }}>
      <Stack.Screen
        name="index"
        options={{
          title: 'Farmer Dashboard',
          headerLeft: () => (
            <Pressable
              onPress={handleLogout}
              style={{ marginRight: 16, padding: 4 }}>
              <Text style={{ color: '#fff', fontSize: 22, fontWeight: 'bold' }}>←</Text>
            </Pressable>
          ),
          headerRight: () => (
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginRight: 4 }}>
              <Pressable
                onPress={() => router.push('/farmer/subscription' as Href)}
                style={{
                  backgroundColor: 'rgba(255,255,255,0.25)',
                  paddingHorizontal: 9,
                  paddingVertical: 6,
                  borderRadius: 8,
                }}>
                <Text style={{ color: '#fff', fontSize: 12, fontWeight: '700' }}>⭐ Plans</Text>
              </Pressable>
              <Pressable
                onPress={() => router.push('/profile' as Href)}
                style={{
                  backgroundColor: 'rgba(255,255,255,0.22)',
                  paddingHorizontal: 9,
                  paddingVertical: 6,
                  borderRadius: 8,
                }}>
                <Text style={{ color: '#fff', fontSize: 12, fontWeight: '700' }}>👤 Profile</Text>
              </Pressable>
              <Pressable
                onPress={handleLogout}
                style={{
                  backgroundColor: 'rgba(255,255,255,0.22)',
                  paddingHorizontal: 9,
                  paddingVertical: 6,
                  borderRadius: 8,
                }}>
                <Text style={{ color: '#fff', fontSize: 12, fontWeight: '700' }}>🚪 Log Out</Text>
              </Pressable>
            </View>
          ),
        }}
      />
      <Stack.Screen
        name="subscription"
        options={{
          title: 'Farmer Subscriptions & Plans',
          headerLeft: () => (
            <Pressable
              onPress={navigateBack}
              style={{ marginRight: 16, padding: 4 }}>
              <Text style={{ color: '#fff', fontSize: 22, fontWeight: 'bold' }}>←</Text>
            </Pressable>
          ),
        }}
      />
      <Stack.Screen
        name="new-listing"
        options={{
          title: 'Add Produce Listing',
          headerLeft: () => (
            <Pressable
              onPress={navigateBack}
              style={{ marginRight: 16, padding: 4 }}>
              <Text style={{ color: '#fff', fontSize: 22, fontWeight: 'bold' }}>←</Text>
            </Pressable>
          ),
        }}
      />
      <Stack.Screen
        name="orders"
        options={{
          title: 'Customer Orders',
          headerLeft: () => (
            <Pressable
              onPress={navigateBack}
              style={{ marginRight: 16, padding: 4 }}>
              <Text style={{ color: '#fff', fontSize: 22, fontWeight: 'bold' }}>←</Text>
            </Pressable>
          ),
        }}
      />
    </Stack>
  </RoleGate>;
}
