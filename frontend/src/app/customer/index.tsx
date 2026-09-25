import { StyleSheet, ScrollView } from 'react-native';
import React from 'react';
import WelcomeCard from '../../components/WelcomeCard';
import { Colors } from '../../constants/theme';

export default function CustomerDashboard() {
  return (
    <ScrollView style={styles.container}>
      <WelcomeCard 
        title="Welcome to Mavuno!" 
        subtitle="Browse fresh produce directly from local farms."
        backgroundColor={Colors.brandGreen}
      />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
    paddingHorizontal: 16,
    paddingTop: 10,
  },
});