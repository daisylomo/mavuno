import { View, Text, StyleSheet } from 'react-native';
import { Link } from 'expo-router';
import React from 'react';

export default function RoleSelector() {
  return (
    <View style={styles.container}>
      <Text style={styles.title}>Mavuno Dev - Select Role</Text>
      
      <Link href="/auth/login" style={StyleSheet.flatten([styles.button, styles.farmerBtn])}>
        Go to Farmer
      </Link>

      <Link href="/customer" style={StyleSheet.flatten([styles.button, styles.customerBtn])}>
        Go to Customer
      </Link>

      <Link href="/admin" style={StyleSheet.flatten([styles.button, styles.adminBtn])}>
        Go to Admin
      </Link>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: '#f5f5f5', padding: 20 },
  title: { fontSize: 24, fontWeight: 'bold', marginBottom: 40 },
  button: { padding: 15, borderRadius: 8, width: '80%', textAlign: 'center', marginBottom: 15, color: '#fff', fontWeight: 'bold', fontSize: 16, overflow: 'hidden' },
  farmerBtn: { backgroundColor: '#4CAF50' },
  customerBtn: { backgroundColor: '#2196F3' },
  adminBtn: { backgroundColor: '#333333' },
});