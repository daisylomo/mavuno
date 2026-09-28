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
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginRight: 4 }}>
              <Pressable
                onPress={() => router.push('/profile' as Href)}
                style={{
                  backgroundColor: 'rgba(255,255,255,0.22)',
                  paddingHorizontal: 10,
                  paddingVertical: 6,
                  borderRadius: 8,
                }}>
                <Text style={{ color: '#fff', fontSize: 13, fontWeight: '700' }}>👤 Profile</Text>
              </Pressable>
              <Pressable
                onPress={handleLogout}
                style={{
                  backgroundColor: 'rgba(255,255,255,0.22)',
                  paddingHorizontal: 10,
                  paddingVertical: 6,
                  borderRadius: 8,
                }}>
                <Text style={{ color: '#fff', fontSize: 13, fontWeight: '700' }}>🚪 Log Out</Text>
              </Pressable>
            </View>
          ),
        }}
      />
      <Stack.Screen
        name="new-listing"
        options={{
          title: 'Add Produce Listing',
        }}
      />
      <Stack.Screen
        name="orders"
        options={{
          title: 'Customer Orders',
        }}
      />
    </Stack>
  </RoleGate>;
}
