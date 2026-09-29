import { StyleSheet, ScrollView } from 'react-native';
import React from 'react';
import WelcomeCard from '../../components/WelcomeCard';
import { Colors } from '../../constants/theme';

export default function AdminDashboard() {
  return (
    <ScrollView style={styles.container}>
      <WelcomeCard 
        title="Admin Portal" 
        subtitle="Monitor marketplace activity and user accounts."
        backgroundColor={Colors.adminSlate}
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