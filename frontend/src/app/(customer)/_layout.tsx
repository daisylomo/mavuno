import { Stack } from 'expo-router';
import React from 'react';

export default function CustomerLayout() {
  return (
    <Stack
      screenOptions={{
        headerStyle: {
          backgroundColor: '#2196F3', // Blue theme for customers
        },
        headerTintColor: '#fff',
        headerTitleStyle: {
          fontWeight: 'bold',
        },
      }}
    >
      <Stack.Screen 
        name="index" 
        options={{ title: 'Marketplace' }} 
      />
    </Stack>
  );
}