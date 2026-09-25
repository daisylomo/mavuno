import { View, Text, StyleSheet, ScrollView, Pressable } from 'react-native';
import React, { useState } from 'react';
import CustomInput from '../../components/CustomInput';
import { Colors } from '../../constants/theme';

export default function ProfileSettings() {
  const [name, setName] = useState('Elavaza Sandra Waiyego');
  const [phone, setPhone] = useState('+254 700 000000');
  const [location, setLocation] = useState('Madaraka, Nairobi');

  return (
    <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
      <View style={styles.avatarPlaceholder}>
        <Text style={styles.avatarText}>{name.charAt(0)}</Text>
      </View>

      <View style={styles.formCard}>
        <CustomInput 
          label="Full Name" 
          value={name} 
          onChangeText={setName} 
        />
        <CustomInput 
          label="Phone Number (M-Pesa)" 
          value={phone} 
          onChangeText={setPhone} 
          keyboardType="phone-pad"
        />
        <CustomInput 
          label="Primary Location" 
          value={location} 
          onChangeText={setLocation} 
        />

        <Pressable style={styles.saveButton}>
          <Text style={styles.saveButtonText}>Save Changes</Text>
        </Pressable>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flexGrow: 1,
    backgroundColor: Colors.background,
    padding: 16,
    alignItems: 'center',
  },
  avatarPlaceholder: {
    width: 100,
    height: 100,
    borderRadius: 50,
    backgroundColor: Colors.brandGreen,
    justifyContent: 'center',
    alignItems: 'center',
    marginVertical: 24,
    elevation: 3,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.2,
    shadowRadius: 4,
  },
  avatarText: {
    color: '#fff',
    fontSize: 40,
    fontWeight: 'bold',
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
  },
  saveButton: {
    backgroundColor: Colors.brandGreen,
    padding: 16,
    borderRadius: 8,
    alignItems: 'center',
    marginTop: 10,
  },
  saveButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: 'bold',
  },
});