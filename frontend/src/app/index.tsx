import { Redirect } from 'expo-router';
import React from 'react';

export default function Index() {
  // Bypasses the old role selector and pushes the user directly to the login screen
  return <Redirect href="/auth/login" />;
}