import { StyleSheet, ScrollView } from 'react-native';
import React from 'react';
import WelcomeCard from '../../components/WelcomeCard';
import { Colors } from '../../constants/theme';

export default function FarmerDashboard() {
  return (
    <ScrollView style={styles.container}>
      <WelcomeCard 
        title="Hello, Farmer!" 
        subtitle="Manage your harvest and orders."
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