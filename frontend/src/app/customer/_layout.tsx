import { Stack, useRouter } from 'expo-router';
import { Pressable, Text } from 'react-native';
import React from 'react';
import { Colors } from '../../constants/theme';
import RoleGate from '../../components/role-gate';

export default function CustomerLayout() {
  const router = useRouter();

  return <RoleGate allowedRoles={['customer']}>
    <Stack
      screenOptions={{
        headerStyle: { backgroundColor: Colors.brandGreen },
        headerTintColor: '#fff',
        headerTitleStyle: { fontWeight: 'bold' },
      }}
    >
      <Stack.Screen 
        name="index" 
        options={{ 
          title: 'Mavuno Market',
          headerLeft: () => (
            <Pressable onPress={() => router.replace('/')} style={{ marginRight: 20, padding: 5 }}>
              <Text style={{ color: '#fff', fontSize: 24, fontWeight: 'bold' }}>←</Text>
            </Pressable>
          ),
        }} 
      />
    </Stack>
  </RoleGate>;
}
