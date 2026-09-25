import { Stack } from 'expo-router';
import React from 'react';

export default function FarmerLayout() {
  return (
    <Stack
      screenOptions={{
        headerStyle: {
          backgroundColor: '#4CAF50', // Example specific to Farmer theme
        },
        headerTintColor: '#fff',
        headerTitleStyle: {
          fontWeight: 'bold',
        },
      }}
    >
      {/* The index.tsx file in this folder will automatically map to this screen */}
      <Stack.Screen 
        name="index" 
        options={{ title: 'Farmer Dashboard' }} 
      />
      {/* Future screens like 'inventory.tsx' will be added here */}
    </Stack>
  );
}