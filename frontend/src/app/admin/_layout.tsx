import { Stack, useRouter } from 'expo-router';
import { Pressable, Text } from 'react-native';
import React from 'react';
import { Colors } from '../../constants/theme';
import RoleGate from '../../components/role-gate';

export default function AdminLayout() {
  const router = useRouter();

  return <RoleGate allowedRoles={['admin']}>
    <Stack
      screenOptions={{
        headerStyle: { backgroundColor: Colors.adminSlate },
        headerTintColor: '#fff',
        headerTitleStyle: { fontWeight: 'bold' },
      }}
    >
      <Stack.Screen 
        name="index" 
        options={{ 
          title: 'Admin Control',
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
