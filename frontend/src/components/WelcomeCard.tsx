import React from 'react';
import { View, Text, StyleSheet } from 'react-native';

interface WelcomeCardProps {
  title: string;
  subtitle: string;
  backgroundColor: string;
}

export default function WelcomeCard({ title, subtitle, backgroundColor }: WelcomeCardProps) {
  return (
    <View style={[styles.card, { backgroundColor }]}>
      <Text style={styles.title}>{title}</Text>
      <Text style={styles.subtitle}>{subtitle}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    padding: 20,
    borderRadius: 16,
    marginVertical: 15,
    // Soft shadow for a modern, elevated look
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.1,
    shadowRadius: 6,
    elevation: 4, 
  },
  title: {
    color: '#ffffff',
    fontSize: 24,
    fontWeight: 'bold',
    marginBottom: 8,
  },
  subtitle: {
    color: '#ffffff',
    fontSize: 16,
    opacity: 0.9,
  },
});