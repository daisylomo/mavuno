import { Stack } from 'expo-router';
import React from 'react';

export default function RootLayout() {
  // Keeping this clean allows Expo Router to handle the new login redirect naturally
  return (
    <Stack screenOptions={{ headerShown: false }} />
  );
}