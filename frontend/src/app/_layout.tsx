import { Stack } from 'expo-router';
import React from 'react';

import { RevenueCatProvider } from '@/providers/revenuecat-provider';

export default function RootLayout() {
  // A blank stack with no headers allows the router to dynamically find any folder you create
  return (
    <RevenueCatProvider>
        <Stack screenOptions={{ headerShown: false }} />
    </RevenueCatProvider>
  );
}