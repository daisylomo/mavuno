import { View, Text, StyleSheet } from 'react-native';
import React from 'react';

export default function AdminDashboard() {
  return (
    <View style={styles.container}>
      <Text style={styles.text}>System Overview & Admin Tools</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#e0e0e0',
  },
  text: {
    fontSize: 20,
    fontWeight: 'bold',
  },
});