import { View, Text, StyleSheet } from 'react-native';
import React from 'react';

export default function CustomerDashboard() {
  return (
    <View style={styles.container}>
      <Text style={styles.text}>Welcome to the Customer Marketplace</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#f5f5f5',
  },
  text: {
    fontSize: 20,
    fontWeight: 'bold',
  },
});