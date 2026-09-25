import { View, Text, TextInput, StyleSheet, Pressable } from 'react-native';
import { useRouter } from 'expo-router';
import React, { useState } from 'react';
import { Colors } from '../../constants/theme';

export default function LoginScreen() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  return (
    <View style={styles.container}>
      <Text style={styles.brandTitle}>Mavuno</Text>
      <Text style={styles.subtitle}>Welcome back. Log in to continue.</Text>

      <View style={styles.formContainer}>
        <Text style={styles.label}>Email Address</Text>
        <TextInput 
          style={styles.input} 
          placeholder="Enter your email" 
          value={email}
          onChangeText={setEmail}
          keyboardType="email-address"
          autoCapitalize="none"
        />

        <Text style={styles.label}>Password</Text>
        <TextInput 
          style={styles.input} 
          placeholder="Enter your password" 
          value={password}
          onChangeText={setPassword}
          secureTextEntry
        />

        <Pressable 
          style={styles.primaryButton} 
          onPress={() => router.replace('/')} 
        >
          <Text style={styles.buttonText}>Log In</Text>
        </Pressable>
      </View>

      <View style={styles.footer}>
        <Text style={styles.footerText}>Don't have an account? </Text>
        <Pressable onPress={() => router.push('/auth/signup')}>
          <Text style={styles.linkText}>Sign Up</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background, justifyContent: 'center', padding: 24 },
  brandTitle: { fontSize: 40, fontWeight: 'bold', color: Colors.brandGreen, textAlign: 'center', marginBottom: 8 },
  subtitle: { fontSize: 16, color: Colors.textMuted, textAlign: 'center', marginBottom: 40 },
  formContainer: { backgroundColor: Colors.surface, padding: 20, borderRadius: 16, elevation: 2, shadowColor: '#000', shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.05, shadowRadius: 4 },
  label: { fontSize: 14, fontWeight: '600', color: Colors.text, marginBottom: 8 },
  input: { backgroundColor: Colors.background, borderWidth: 1, borderColor: '#E9ECEF', borderRadius: 8, padding: 14, fontSize: 16, marginBottom: 20 },
  primaryButton: { backgroundColor: Colors.brandGreen, padding: 16, borderRadius: 8, alignItems: 'center', marginTop: 10 },
  buttonText: { color: '#fff', fontSize: 16, fontWeight: 'bold' },
  footer: { flexDirection: 'row', justifyContent: 'center', marginTop: 30 },
  footerText: { color: Colors.textMuted, fontSize: 15 },
  linkText: { color: Colors.brandGreen, fontSize: 15, fontWeight: 'bold' },
});