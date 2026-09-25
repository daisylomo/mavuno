import { View, Text, TextInput, StyleSheet, Pressable, ScrollView } from 'react-native';
import { useRouter } from 'expo-router';
import React, { useState } from 'react';
import { Colors } from '../../constants/theme';

export default function SignUpScreen() {
  const router = useRouter();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState<'customer' | 'farmer'>('customer');

  const handleSignUp = () => {
    if (role === 'farmer') {
      router.replace('/farmer');
    } else {
      router.replace('/customer');
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.scrollContainer} keyboardShouldPersistTaps="handled">
      <View style={styles.container}>
        <Text style={styles.brandTitle}>Join Mavuno</Text>
        <Text style={styles.subtitle}>Connect directly with local produce.</Text>

        <View style={styles.formContainer}>
          <Text style={styles.label}>I want to...</Text>
          <View style={styles.roleContainer}>
            <Pressable 
              style={[
                styles.roleCard, 
                role === 'customer' && { borderColor: Colors.brandGreen, backgroundColor: '#E8F5E9' }
              ]}
              onPress={() => setRole('customer')}
            >
              <Text style={[styles.roleTitle, role === 'customer' && { color: Colors.brandGreen }]}>Buy Produce</Text>
              <Text style={styles.roleSubtitle}>Customer</Text>
            </Pressable>

            <Pressable 
              style={[
                styles.roleCard, 
                role === 'farmer' && { borderColor: Colors.brandGreen, backgroundColor: '#E8F5E9' }
              ]}
              onPress={() => setRole('farmer')}
            >
              <Text style={[styles.roleTitle, role === 'farmer' && { color: Colors.brandGreen }]}>Sell Produce</Text>
              <Text style={styles.roleSubtitle}>Farmer</Text>
            </Pressable>
          </View>

          <Text style={styles.label}>Full Name</Text>
          <TextInput 
            style={styles.input} 
            placeholder="Enter your full name" 
            value={name}
            onChangeText={setName}
          />

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
            placeholder="Create a password" 
            value={password}
            onChangeText={setPassword}
            secureTextEntry
          />

          <Pressable style={styles.primaryButton} onPress={handleSignUp}>
            <Text style={styles.buttonText}>Create Account</Text>
          </Pressable>
        </View>

        <View style={styles.footer}>
          <Text style={styles.footerText}>Already have an account? </Text>
          <Pressable onPress={() => router.push('/auth/login')}>
            <Text style={styles.linkText}>Log In</Text>
          </Pressable>
        </View>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scrollContainer: { flexGrow: 1, backgroundColor: Colors.background },
  container: { flex: 1, justifyContent: 'center', padding: 24, paddingTop: 60 },
  brandTitle: { fontSize: 40, fontWeight: 'bold', color: Colors.brandGreen, textAlign: 'center', marginBottom: 8 },
  subtitle: { fontSize: 16, color: Colors.textMuted, textAlign: 'center', marginBottom: 30 },
  formContainer: { backgroundColor: Colors.surface, padding: 20, borderRadius: 16, elevation: 2, shadowColor: '#000', shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.05, shadowRadius: 4 },
  
  roleContainer: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 20 },
  roleCard: { flex: 1, borderWidth: 1, borderColor: '#E9ECEF', borderRadius: 8, padding: 12, marginHorizontal: 4, alignItems: 'center', backgroundColor: Colors.background },
  roleTitle: { fontSize: 15, fontWeight: 'bold', color: Colors.text, marginBottom: 4 },
  roleSubtitle: { fontSize: 12, color: Colors.textMuted },
  
  label: { fontSize: 14, fontWeight: '600', color: Colors.text, marginBottom: 8 },
  input: { backgroundColor: Colors.background, borderWidth: 1, borderColor: '#E9ECEF', borderRadius: 8, padding: 14, fontSize: 16, marginBottom: 20 },
  primaryButton: { backgroundColor: Colors.brandGreen, padding: 16, borderRadius: 8, alignItems: 'center', marginTop: 10 },
  buttonText: { color: '#fff', fontSize: 16, fontWeight: 'bold' },
  footer: { flexDirection: 'row', justifyContent: 'center', marginTop: 30, marginBottom: 40 },
  footerText: { color: Colors.textMuted, fontSize: 15 },
  linkText: { color: Colors.brandGreen, fontSize: 15, fontWeight: 'bold' },
});