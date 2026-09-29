import React, { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { Href, useRouter } from 'expo-router';
import { Colors } from '../../constants/theme';
import { userService } from '../../services/user-service';
import { wakeServer } from '../../components/customer-catalog-api';
import { PASSWORD_MIN_LENGTH } from '../../services/auth-api';

type RegisterRole = 'customer' | 'farmer';

interface RoleOption {
  key: RegisterRole;
  emoji: string;
  title: string;
  subtitle: string;
  themeColor: string;
  badgeBg: string;
}

const ROLES: RoleOption[] = [
  {
    key: 'customer',
    emoji: '🛒',
    title: 'Customer (Buyer)',
    subtitle: 'Browse & buy fresh produce directly from local farmers',
    themeColor: '#2563EB',
    badgeBg: '#EFF6FF',
  },
  {
    key: 'farmer',
    emoji: '🌾',
    title: 'Farmer / Producer',
    subtitle: 'Sell your harvest directly, manage listings & receive orders',
    themeColor: '#16A34A',
    badgeBg: '#F0FDF4',
  },
];

export default function SignUpScreen() {
  const router = useRouter();

  const [selectedRole, setSelectedRole] = useState<RegisterRole>('farmer');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');

  useEffect(() => {
    // The hosted API sleeps when idle; start waking it while the person types.
    try { wakeServer(); } catch { /* an invalid API URL is reported when submitting */ }
  }, []);

  const handleSignUp = async () => {
    if (!name.trim()) {
      setErrorMessage(
        selectedRole === 'farmer'
          ? 'Please enter your farm or business name'
          : 'Please enter your full name'
      );
      return;
    }
    if (!email.trim() && !phone.trim()) {
      setErrorMessage('Please provide an email address or phone number');
      return;
    }
    if (!password || password.length < PASSWORD_MIN_LENGTH) {
      setErrorMessage(`Password must be at least ${PASSWORD_MIN_LENGTH} characters long`);
      return;
    }

    setErrorMessage('');
    setLoading(true);

    try {
      await userService.register({
        name: name.trim(),
        email: email.trim(),
        phone: phone.trim(),
        password,
        role: selectedRole,
      });

      // Ensure any previous session is cleared so the new account logs in cleanly
      await userService.logout();

      if (Platform.OS === 'web') {
        alert('Account created successfully! Please log in to your account.');
        router.replace('/auth/login' as Href);
      } else {
        Alert.alert(
          'Account Created',
          'Your account has been created successfully! Please log in.',
          [
            {
              text: 'Log In Now',
              onPress: () => router.replace('/auth/login' as Href),
            },
          ]
        );
      }
    } catch (err: any) {
      setErrorMessage(err.message || 'Registration failed. Please try again.');
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      style={styles.keyboardContainer}>
      <ScrollView
        contentContainerStyle={styles.scrollContainer}
        keyboardShouldPersistTaps="handled">
        {/* Brand Header with Circular Logo */}
        <View style={styles.brandHeader}>
          <View style={styles.logoCircle}>
            <Text style={styles.logoIcon}>🌾</Text>
          </View>
          <Text style={styles.appName}>Mavuno</Text>
          <Text style={styles.tagline}>Direct Farm-to-Consumer Marketplace</Text>
        </View>

        {/* Card */}
        <View style={styles.card}>
          <Text style={styles.title}>Create Account</Text>
          <Text style={styles.subtitle}>Choose whether you are buying or selling produce</Text>

          <Text style={styles.sectionHeader}>1. CHOOSE YOUR ACCOUNT TYPE</Text>

          {/* Role Selection Cards: Customer or Farmer only */}
          <View style={styles.rolesList}>
            {ROLES.map((role) => {
              const isSelected = selectedRole === role.key;
              return (
                <TouchableOpacity
                  key={role.key}
                  style={[
                    styles.roleCard,
                    isSelected && {
                      borderColor: role.themeColor,
                      backgroundColor: role.badgeBg,
                      borderWidth: 2,
                    },
                  ]}
                  onPress={() => setSelectedRole(role.key)}
                  activeOpacity={0.8}>
                  <View style={styles.roleCardLeft}>
                    <Text style={styles.roleEmoji}>{role.emoji}</Text>
                    <View style={styles.roleTextContainer}>
                      <Text
                        style={[
                          styles.roleTitle,
                          isSelected && { color: role.themeColor, fontWeight: '700' },
                        ]}>
                        {role.title}
                      </Text>
                      <Text style={styles.roleSubtitle}>{role.subtitle}</Text>
                    </View>
                  </View>
                  <View
                    style={[
                      styles.radioCircle,
                      isSelected && { borderColor: role.themeColor },
                    ]}>
                    {isSelected && (
                      <View
                        style={[
                          styles.radioInnerCircle,
                          { backgroundColor: role.themeColor },
                        ]}
                      />
                    )}
                  </View>
                </TouchableOpacity>
              );
            })}
          </View>

          <Text style={[styles.sectionHeader, { marginTop: 22 }]}>
            2. ACCOUNT DETAILS
          </Text>

          {errorMessage ? (
            <View style={styles.errorBanner}>
              <Text style={styles.errorText}>{errorMessage}</Text>
            </View>
          ) : null}

          {/* Name Field */}
          <View style={styles.inputGroup}>
            <Text style={styles.label}>
              {selectedRole === 'farmer' ? 'Farm / Business Name' : 'Full Name'}
            </Text>
            <TextInput
              style={styles.input}
              placeholder={
                selectedRole === 'farmer' ? 'e.g. Kiambu Fresh Greens' : 'e.g. Jane Mwangi'
              }
              placeholderTextColor="#9CA3AF"
              value={name}
              onChangeText={setName}
            />
          </View>

          {/* Email */}
          <View style={styles.inputGroup}>
            <Text style={styles.label}>Email Address</Text>
            <TextInput
              style={styles.input}
              placeholder="e.g. user@mavuno.com"
              placeholderTextColor="#9CA3AF"
              value={email}
              onChangeText={setEmail}
              keyboardType="email-address"
              autoCapitalize="none"
            />
          </View>

          {/* Phone */}
          <View style={styles.inputGroup}>
            <Text style={styles.label}>Phone Number (M-Pesa enabled)</Text>
            <TextInput
              style={styles.input}
              placeholder="e.g. +254 712 345678"
              placeholderTextColor="#9CA3AF"
              value={phone}
              onChangeText={setPhone}
              keyboardType="phone-pad"
            />
          </View>

          {/* Password */}
          <View style={styles.inputGroup}>
            <Text style={styles.label}>Password</Text>
            <TextInput
              style={styles.input}
              placeholder={`At least ${PASSWORD_MIN_LENGTH} characters`}
              placeholderTextColor="#9CA3AF"
              value={password}
              onChangeText={setPassword}
              secureTextEntry
            />
          </View>

          {/* Submit */}
          <TouchableOpacity
            style={[styles.submitButton, loading && styles.buttonDisabled]}
            onPress={handleSignUp}
            disabled={loading}
            activeOpacity={0.8}>
            {loading ? (
              <ActivityIndicator color="#FFFFFF" />
            ) : (
              <Text style={styles.submitButtonText}>
                Create Account & Proceed to Log In
              </Text>
            )}
          </TouchableOpacity>
          {loading && (
            <Text style={styles.wakeHint}>
              The first sign-in after a quiet spell can take up to a minute while the server starts.
            </Text>
          )}

          {/* Back to Login */}
          <View style={styles.footerRow}>
            <Text style={styles.footerText}>Already have an account? </Text>
            <TouchableOpacity onPress={() => router.push('/auth/login' as Href)}>
              <Text style={styles.footerLink}>Log in</Text>
            </TouchableOpacity>
          </View>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  wakeHint: {
    color: '#64748B',
    fontSize: 12,
    textAlign: 'center',
    marginTop: 8,
  },
  keyboardContainer: {
    flex: 1,
    backgroundColor: '#F7FAF7',
  },
  scrollContainer: {
    flexGrow: 1,
    justifyContent: 'center',
    paddingHorizontal: 24,
    paddingVertical: 40,
  },
  brandHeader: {
    alignItems: 'center',
    marginBottom: 24,
  },
  logoCircle: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: '#E8F5E9',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 10,
    borderWidth: 1.5,
    borderColor: '#C8E6C9',
  },
  logoIcon: {
    fontSize: 32,
  },
  appName: {
    fontSize: 28,
    fontWeight: '800',
    color: '#1B5E20',
    letterSpacing: 0.5,
  },
  tagline: {
    fontSize: 14,
    color: '#4B5563',
    marginTop: 4,
    textAlign: 'center',
  },
  card: {
    backgroundColor: '#FFFFFF',
    borderRadius: 20,
    padding: 24,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.08,
    shadowRadius: 12,
    elevation: 3,
    borderWidth: 1,
    borderColor: '#E5E7EB',
  },
  title: {
    fontSize: 22,
    fontWeight: '700',
    color: '#111827',
  },
  subtitle: {
    fontSize: 14,
    color: '#6B7280',
    marginTop: 4,
    marginBottom: 18,
  },
  sectionHeader: {
    fontSize: 11,
    fontWeight: '700',
    color: '#6B7280',
    letterSpacing: 0.8,
    marginBottom: 10,
  },
  rolesList: {
    gap: 12,
  },
  roleCard: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: 14,
    borderRadius: 14,
    borderWidth: 1.5,
    borderColor: '#E5E7EB',
    backgroundColor: '#FAFAFA',
  },
  roleCardLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
    gap: 12,
  },
  roleEmoji: {
    fontSize: 26,
  },
  roleTextContainer: {
    flex: 1,
  },
  roleTitle: {
    fontSize: 15,
    fontWeight: '600',
    color: '#1F2937',
  },
  roleSubtitle: {
    fontSize: 12,
    color: '#6B7280',
    marginTop: 2,
  },
  radioCircle: {
    width: 22,
    height: 22,
    borderRadius: 11,
    borderWidth: 2,
    borderColor: '#D1D5DB',
    justifyContent: 'center',
    alignItems: 'center',
    marginLeft: 8,
  },
  radioInnerCircle: {
    width: 12,
    height: 12,
    borderRadius: 6,
  },
  errorBanner: {
    backgroundColor: '#FEE2E2',
    borderWidth: 1,
    borderColor: '#FCA5A5',
    borderRadius: 8,
    padding: 10,
    marginBottom: 16,
  },
  errorText: {
    color: '#991B1B',
    fontSize: 13,
  },
  inputGroup: {
    marginBottom: 14,
  },
  label: {
    fontSize: 13,
    fontWeight: '600',
    color: '#374151',
    marginBottom: 6,
  },
  input: {
    backgroundColor: '#F9FAFB',
    borderWidth: 1,
    borderColor: '#D1D5DB',
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 15,
    color: '#111827',
  },
  submitButton: {
    backgroundColor: Colors.brandGreen,
    borderRadius: 10,
    paddingVertical: 14,
    alignItems: 'center',
    marginTop: 14,
  },
  buttonDisabled: {
    opacity: 0.7,
  },
  submitButtonText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '700',
  },
  footerRow: {
    flexDirection: 'row',
    justifyContent: 'center',
    marginTop: 20,
  },
  footerText: {
    fontSize: 14,
    color: '#6B7280',
  },
  footerLink: {
    fontSize: 14,
    fontWeight: '700',
    color: Colors.brandGreen,
  },
});