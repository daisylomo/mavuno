import { Stack, useRouter } from 'expo-router';
import { Pressable, Text } from 'react-native';
import React from 'react';
import { Colors } from '../../constants/theme';

export default function ProfileLayout() {
  const router = useRouter();

  return (
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
          title: 'Account Settings',
          headerLeft: () => (
            <Pressable onPress={() => router.back()} style={{ marginRight: 20, padding: 5 }}>
              <Text style={{ color: '#fff', fontSize: 24, fontWeight: 'bold' }}>←</Text>
            </Pressable>
          ),
        }} 
      />
    </Stack>
  );
}