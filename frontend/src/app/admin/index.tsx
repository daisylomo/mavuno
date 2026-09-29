import { StyleSheet, ScrollView, Text, Pressable, Linking } from 'react-native';
import React, { useState } from 'react';
import { apiBaseUrl } from '../../components/customer-catalog-api';
import WelcomeCard from '../../components/WelcomeCard';
import { Colors } from '../../constants/theme';

export default function AdminDashboard() {
  const [error, setError] = useState('');
  const openPortal = async () => {
    try {
      const base = apiBaseUrl();
      if (!base) throw new Error('Configure the live API to use the administrator portal.');
      await Linking.openURL(`${new URL(base).origin}/admin`);
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not open the admin portal.'); }
  };
  return (
    <ScrollView style={styles.container}>
      <WelcomeCard 
        title="Admin Portal" 
        subtitle="Monitor marketplace activity and user accounts."
        backgroundColor={Colors.adminSlate}
      />
      <Text style={styles.description}>Manage produce categories, catalog types and outstanding refunds through the secure browser portal.</Text>
      <Pressable accessibilityRole="button" style={styles.button} onPress={openPortal}>
        <Text style={styles.buttonText}>Open browser admin portal</Text>
      </Pressable>
      {!!error && <Text accessibilityRole="alert" style={styles.description}>{error}</Text>}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  description: { paddingVertical: 20, fontSize: 16, lineHeight: 24 },
  button: { backgroundColor: Colors.adminSlate, padding: 16, borderRadius: 8 },
  buttonText: { color: '#fff', fontWeight: '700', textAlign: 'center' },
  container: {
    flex: 1,
    backgroundColor: Colors.background,
    paddingHorizontal: 16,
    paddingTop: 10,
  },
});
