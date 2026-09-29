import { Stack } from 'expo-router';
import React from 'react';

export default function RootLayout() {
  // A blank stack with no headers allows the router to dynamically find any folder you create
  return (
    <Stack screenOptions={{ headerShown: false }} />
  );
}