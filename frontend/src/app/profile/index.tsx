import React, { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Platform,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { Href, useRouter } from 'expo-router';
import CustomInput from '../../components/CustomInput';
import { Colors } from '../../constants/theme';
import { AppUser, userService } from '../../services/user-service';
import { isBackendConfigured } from '../../services/auth-api';
import { farmerService } from '../../services/farmer-service';
import { FarmerPublicDetails } from '../../types/farmer';

export default function ProfileSettings() {
  const router = useRouter();

  const [currentUser, setCurrentUser] = useState<AppUser | null>(null);
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [email, setEmail] = useState('');
  const [location, setLocation] = useState('');
  const [loading, setLoading] = useState(true);
  const [savedSuccess, setSavedSuccess] = useState(false);
  const [farm, setFarm] = useState<FarmerPublicDetails | null>(null);
  const [farmMessage, setFarmMessage] = useState<string | null>(null);

  useEffect(() => {
    async function loadUser() {
      try {
        const user = await userService.getCurrentUser();
        if (user) {
          setCurrentUser(user);
          setName(user.name || '');
          setEmail(user.email || '');
          setPhone(user.phone || '');
          setLocation(user.location || 'Nairobi, Kenya');
          if (user.role === 'farmer' && isBackendConfigured()) {
            farmerService.getPublicDetails().then(setFarm).catch(() => setFarmMessage(
              'Could not load your farm details. Pull down or reopen this screen to try again.'));
          }
        }
      } finally {
        setLoading(false);
      }
    }
    loadUser();
  }, []);

  const handleSave = async () => {
    if (!name.trim()) return;
    try {
      const updated = await userService.updateProfile({
        name: name.trim(),
        ...(isBackendConfigured() ? {} : { email: email.trim(), phone: phone.trim(), location: location.trim() }),
      });
      if (updated) {
        setCurrentUser(updated);
        setSavedSuccess(true);
        setTimeout(() => setSavedSuccess(false), 3000);
      }
    } catch (err: any) {
      alert(err.message || 'Failed to update profile');
    }
  };

  const saveFarm = async () => {
    if (!farm) return;
    try {
      await farmerService.savePublicDetails(farm);
      setFarmMessage('Saved. Buyers now see these details on your listings.');
    } catch (err: any) {
      setFarmMessage(err.message || 'Could not save your farm details.');
    }
  };

  const handleLogout = async () => {
    const doLogout = async () => {
      await userService.logout();
      router.replace('/auth/login' as Href);
    };

    if (Platform.OS === 'web') {
      if (window.confirm('Are you sure you want to log out of your account?')) {
        await doLogout();
      }
    } else {
      Alert.alert('Log Out', 'Are you sure you want to log out?', [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Log Out',
          style: 'destructive',
          onPress: doLogout,
        },
      ]);
    }
  };

  if (loading) {
    return (
      <View style={styles.centerContainer}>
        <ActivityIndicator size="large" color={Colors.brandGreen} />
      </View>
    );
  }

  return (
    <ScrollView
      contentContainerStyle={styles.container}
      keyboardShouldPersistTaps="handled">
      {/* Avatar Header */}
      <View style={styles.avatarPlaceholder}>
        <Text style={styles.avatarText}>
          {name ? name.charAt(0).toUpperCase() : '👤'}
        </Text>
      </View>

      <Text style={styles.userName}>{name || 'Mavuno User'}</Text>
      <View style={styles.roleBadge}>
        <Text style={styles.roleBadgeText}>
          {currentUser?.role === 'farmer' ? '🌾 Farmer Account' : '🛒 Customer Account'}
        </Text>
      </View>

      {savedSuccess && (
        <View style={styles.successBanner}>
          <Text style={styles.successText}>✓ Profile changes saved successfully!</Text>
        </View>
      )}

      {/* Profile Details Card */}
      <View style={styles.formCard}>
        <Text style={styles.cardSectionTitle}>Account Details</Text>

        <CustomInput
          label="Full Name / Farm Name"
          value={name}
          onChangeText={setName}
        />

        <CustomInput
          label="Email Address"
          value={email}
          onChangeText={setEmail}
          editable={!isBackendConfigured()}
          keyboardType="email-address"
          autoCapitalize="none"
        />

        <CustomInput
          label="Phone Number (M-Pesa enabled)"
          value={phone}
          onChangeText={setPhone}
          editable={!isBackendConfigured()}
          keyboardType="phone-pad"
        />

        <CustomInput
          label="Primary Farm / Delivery Location"
          value={location}
          onChangeText={setLocation}
          editable={!isBackendConfigured()}
        />

        <TouchableOpacity style={styles.saveButton} onPress={handleSave}>
          <Text style={styles.saveButtonText}>Save Changes</Text>
        </TouchableOpacity>
      </View>

      {farm && (
        <View style={styles.formCard}>
          <Text style={styles.cardSectionTitle}>What buyers see about your farm</Text>
          <Text style={styles.farmHint}>
            These details appear next to every listing so buyers know who grew their food.
          </Text>
          <CustomInput label="Farm name" value={farm.farmName}
            onChangeText={(farmName) => setFarm({ ...farm, farmName })} placeholder="e.g. Kamau Greens" />
          <CustomInput label="Town / area" value={farm.locality}
            onChangeText={(locality) => setFarm({ ...farm, locality })} placeholder="e.g. Limuru" />
          <CustomInput label="County" value={farm.county}
            onChangeText={(county) => setFarm({ ...farm, county })} placeholder="e.g. Kiambu" />
          <CustomInput label="How you farm (in your words)" value={farm.farmingPractices}
            onChangeText={(farmingPractices) => setFarm({ ...farm, farmingPractices })}
            placeholder="e.g. Rain-fed, no synthetic pesticides" />
          <Text style={styles.farmHint}>
            Buyers are told this is your own description, not a certification. Only claim what is true.
          </Text>
          <View style={styles.switchRow}>
            <Text style={styles.switchLabel}>Buyers can collect from the farm</Text>
            <Switch value={farm.offersPickup} onValueChange={(offersPickup) => setFarm({ ...farm, offersPickup })} />
          </View>
          <View style={styles.switchRow}>
            <Text style={styles.switchLabel}>I deliver</Text>
            <Switch value={farm.offersDelivery} onValueChange={(offersDelivery) => setFarm({ ...farm, offersDelivery })} />
          </View>
          {farm.offersDelivery && (
            <CustomInput label="Delivery distance (km)" value={farm.deliveryRadiusKm} keyboardType="number-pad"
              onChangeText={(deliveryRadiusKm) => setFarm({ ...farm, deliveryRadiusKm })} />
          )}
          {!!farmMessage && <Text style={styles.farmHint}>{farmMessage}</Text>}
          <TouchableOpacity style={styles.saveButton} onPress={saveFarm}>
            <Text style={styles.saveButtonText}>Save farm details</Text>
          </TouchableOpacity>
        </View>
      )}
      {!farm && !!farmMessage && <Text style={styles.farmHint}>{farmMessage}</Text>}

      {/* Log Out Section */}
      <View style={styles.logoutCard}>
        <Text style={styles.logoutCardTitle}>Account Session</Text>
        <Text style={styles.logoutCardSubtitle}>
          Sign out of your active account on this device.
        </Text>

        <TouchableOpacity style={styles.logoutButton} onPress={handleLogout}>
          <Text style={styles.logoutButtonText}>🚪 Log Out</Text>
        </TouchableOpacity>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  farmHint: {
    fontSize: 12,
    color: Colors.textMuted,
    marginBottom: 10,
  },
  switchRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 12,
  },
  switchLabel: {
    fontSize: 14,
    color: Colors.text,
    flex: 1,
  },
  container: {
    flexGrow: 1,
    backgroundColor: Colors.background,
    padding: 16,
    paddingBottom: 40,
    alignItems: 'center',
  },
  centerContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: Colors.background,
  },
  avatarPlaceholder: {
    width: 90,
    height: 90,
    borderRadius: 45,
    backgroundColor: Colors.brandGreen,
    justifyContent: 'center',
    alignItems: 'center',
    marginTop: 16,
    marginBottom: 10,
    elevation: 3,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.15,
    shadowRadius: 4,
  },
  avatarText: {
    color: '#fff',
    fontSize: 38,
    fontWeight: 'bold',
  },
  userName: {
    fontSize: 20,
    fontWeight: '800',
    color: Colors.text,
  },
  roleBadge: {
    backgroundColor: '#DCFCE7',
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 12,
    marginTop: 6,
    marginBottom: 16,
  },
  roleBadgeText: {
    fontSize: 12,
    fontWeight: '700',
    color: '#15803D',
  },
  successBanner: {
    width: '100%',
    backgroundColor: '#DCFCE7',
    borderWidth: 1,
    borderColor: '#86EFAC',
    borderRadius: 8,
    padding: 12,
    marginBottom: 14,
    alignItems: 'center',
  },
  successText: {
    color: '#166534',
    fontSize: 14,
    fontWeight: '600',
  },
  formCard: {
    width: '100%',
    backgroundColor: Colors.surface,
    borderRadius: 16,
    padding: 20,
    elevation: 2,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    marginBottom: 16,
  },
  cardSectionTitle: {
    fontSize: 14,
    fontWeight: '700',
    color: Colors.textMuted,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: 16,
  },
  saveButton: {
    backgroundColor: Colors.brandGreen,
    padding: 14,
    borderRadius: 10,
    alignItems: 'center',
    marginTop: 6,
  },
  saveButtonText: {
    color: '#fff',
    fontSize: 15,
    fontWeight: '700',
  },
  logoutCard: {
    width: '100%',
    backgroundColor: Colors.surface,
    borderRadius: 16,
    padding: 20,
    borderWidth: 1,
    borderColor: '#FEE2E2',
  },
  logoutCardTitle: {
    fontSize: 14,
    fontWeight: '700',
    color: '#991B1B',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  logoutCardSubtitle: {
    fontSize: 13,
    color: Colors.textMuted,
    marginTop: 4,
    marginBottom: 16,
  },
  logoutButton: {
    backgroundColor: '#FEE2E2',
    padding: 14,
    borderRadius: 10,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#FCA5A5',
  },
  logoutButtonText: {
    color: '#DC2626',
    fontSize: 15,
    fontWeight: '700',
  },
});
