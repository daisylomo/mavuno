import React from 'react';
import {
  ActivityIndicator,
  Button,
  Text,
  View,
} from 'react-native';

import { useRevenueCat } from '@/providers/revenuecat-provider';

export default function PremiumFeatureScreen() {
  const {
    ready,
    isPremium,
    error,
    presentPaywall,
    restore,
  } = useRevenueCat();

  if (!ready) {
    return <ActivityIndicator />;
  }

  if (!isPremium) {
    return (
      <View style={{ flex: 1, justifyContent: 'center', padding: 24 }}>
        <Text style={{ fontSize: 24, fontWeight: '700' }}>
          Mavuno Premium
        </Text>

        <Text style={{ marginVertical: 16 }}>
          Upgrade to access premium marketplace tools.
        </Text>

        {error ? (
          <Text style={{ color: 'red', marginBottom: 12 }}>
            {error}
          </Text>
        ) : null}

        <Button
          title="View premium plans"
          onPress={() => {
            void presentPaywall();
          }}
        />

        <Button
          title="Restore purchases"
          onPress={() => {
            void restore();
          }}
        />
      </View>
    );
  }

  return (
    <View style={{ flex: 1, padding: 24 }}>
      <Text>Premium content goes here.</Text>
    </View>
  );
}