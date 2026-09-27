import React, { useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Colors } from '@/constants/theme';
import { farmerService } from '@/services/farmer-service';
import { ProduceCategory, ProduceUnit } from '@/types/farmer';

const CATEGORIES: { label: ProduceCategory; icon: string }[] = [
  { label: 'Vegetables', icon: '🥬' },
  { label: 'Fruits', icon: '🥭' },
  { label: 'Grains & Cereals', icon: '🌽' },
  { label: 'Tubers & Roots', icon: '🥔' },
  { label: 'Dairy & Poultry', icon: '🥛' },
];

const UNITS: ProduceUnit[] = ['kg', 'crate', 'bunch', 'bag', 'piece'];

export default function NewListingScreen() {
  const router = useRouter();

  const [title, setTitle] = useState('');
  const [category, setCategory] = useState<ProduceCategory>('Vegetables');
  const [price, setPrice] = useState('');
  const [quantity, setQuantity] = useState('');
  const [unit, setUnit] = useState<ProduceUnit>('kg');
  const [harvestDate, setHarvestDate] = useState('Harvested Today');
  const [description, setDescription] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const handleSave = async () => {
    if (!title.trim()) {
      setError('Please enter the produce name');
      return;
    }
    const numPrice = parseFloat(price);
    if (isNaN(numPrice) || numPrice <= 0) {
      setError('Please enter a valid price per unit');
      return;
    }
    const numQuantity = parseFloat(quantity);
    if (isNaN(numQuantity) || numQuantity <= 0) {
      setError('Please enter available quantity');
      return;
    }

    setError('');
    setSaving(true);

    try {
      await farmerService.createListing({
        title: title.trim(),
        category,
        price: numPrice,
        quantity: numQuantity,
        unit,
        harvestDate: harvestDate.trim() || 'Fresh Harvest',
        description: description.trim() || 'Organically grown fresh harvest.',
        status: numQuantity <= 10 ? 'low_stock' : 'active',
      });

      router.back();
    } catch (err: any) {
      setError(err.message || 'Failed to save listing');
      setSaving(false);
    }
  };

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      style={styles.keyboardContainer}>
      <ScrollView
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled">
        {/* Top Info Banner */}
        <View style={styles.banner}>
          <Text style={styles.bannerEmoji}>🌱</Text>
          <View style={styles.bannerTextContainer}>
            <Text style={styles.bannerTitle}>List Your Fresh Harvest</Text>
            <Text style={styles.bannerSubtitle}>
              Connect directly with customers across the region
            </Text>
          </View>
        </View>

        {error ? (
          <View style={styles.errorBox}>
            <Text style={styles.errorText}>{error}</Text>
          </View>
        ) : null}

        {/* Produce Name */}
        <View style={styles.fieldGroup}>
          <Text style={styles.fieldLabel}>Produce / Crop Name *</Text>
          <TextInput
            style={styles.textInput}
            placeholder="e.g. Fresh Sukuma Wiki, Managu, Hass Avocados"
            placeholderTextColor="#9CA3AF"
            value={title}
            onChangeText={setTitle}
          />
        </View>

        {/* Category Selector */}
        <View style={styles.fieldGroup}>
          <Text style={styles.fieldLabel}>Category *</Text>
          <View style={styles.chipRow}>
            {CATEGORIES.map((cat) => {
              const isSelected = category === cat.label;
              return (
                <TouchableOpacity
                  key={cat.label}
                  style={[
                    styles.chip,
                    isSelected && styles.chipSelected,
                  ]}
                  onPress={() => setCategory(cat.label)}>
                  <Text style={styles.chipIcon}>{cat.icon}</Text>
                  <Text
                    style={[
                      styles.chipText,
                      isSelected && styles.chipTextSelected,
                    ]}>
                    {cat.label}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </View>
        </View>

        {/* Pricing & Units */}
        <View style={styles.twoColumnRow}>
          <View style={[styles.fieldGroup, { flex: 1 }]}>
            <Text style={styles.fieldLabel}>Price (KSh) *</Text>
            <TextInput
              style={styles.textInput}
              placeholder="e.g. 50"
              placeholderTextColor="#9CA3AF"
              keyboardType="numeric"
              value={price}
              onChangeText={setPrice}
            />
          </View>

          <View style={[styles.fieldGroup, { flex: 1 }]}>
            <Text style={styles.fieldLabel}>Available Stock *</Text>
            <TextInput
              style={styles.textInput}
              placeholder="e.g. 100"
              placeholderTextColor="#9CA3AF"
              keyboardType="numeric"
              value={quantity}
              onChangeText={setQuantity}
            />
          </View>
        </View>

        {/* Unit of Measurement */}
        <View style={styles.fieldGroup}>
          <Text style={styles.fieldLabel}>Unit of Sale *</Text>
          <View style={styles.unitRow}>
            {UNITS.map((u) => {
              const isSelected = unit === u;
              return (
                <TouchableOpacity
                  key={u}
                  style={[styles.unitChip, isSelected && styles.unitChipSelected]}
                  onPress={() => setUnit(u)}>
                  <Text
                    style={[
                      styles.unitChipText,
                      isSelected && styles.unitChipTextSelected,
                    ]}>
                    per {u}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </View>
        </View>

        {/* Harvest Date Presets */}
        <View style={styles.fieldGroup}>
          <Text style={styles.fieldLabel}>Harvest Freshness</Text>
          <View style={styles.presetRow}>
            {['Harvested Today', 'Harvested Yesterday', 'Harvesting Tomorrow'].map((preset) => {
              const isSelected = harvestDate === preset;
              return (
                <TouchableOpacity
                  key={preset}
                  style={[
                    styles.presetPill,
                    isSelected && styles.presetPillSelected,
                  ]}
                  onPress={() => setHarvestDate(preset)}>
                  <Text
                    style={[
                      styles.presetText,
                      isSelected && styles.presetTextSelected,
                    ]}>
                    {preset}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </View>
        </View>

        {/* Description */}
        <View style={styles.fieldGroup}>
          <Text style={styles.fieldLabel}>Description & Farming Notes</Text>
          <TextInput
            style={[styles.textInput, styles.textArea]}
            placeholder="Tell buyers about how this was grown, quality, freshness, or minimum order..."
            placeholderTextColor="#9CA3AF"
            multiline
            numberOfLines={4}
            value={description}
            onChangeText={setDescription}
          />
        </View>

        {/* Submit Button */}
        <TouchableOpacity
          style={[styles.publishButton, saving && styles.buttonDisabled]}
          onPress={handleSave}
          disabled={saving}
          activeOpacity={0.8}>
          {saving ? (
            <ActivityIndicator color="#FFFFFF" />
          ) : (
            <Text style={styles.publishButtonText}>Publish Produce to Marketplace</Text>
          )}
        </TouchableOpacity>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  keyboardContainer: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  content: {
    padding: 16,
    paddingBottom: 40,
  },
  banner: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#E8F5E9',
    borderRadius: 14,
    padding: 16,
    marginBottom: 20,
    borderWidth: 1,
    borderColor: '#C8E6C9',
  },
  bannerEmoji: {
    fontSize: 32,
    marginRight: 14,
  },
  bannerTextContainer: {
    flex: 1,
  },
  bannerTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: Colors.brandGreen,
  },
  bannerSubtitle: {
    fontSize: 13,
    color: '#4B5563',
    marginTop: 2,
  },
  errorBox: {
    backgroundColor: '#FEE2E2',
    borderWidth: 1,
    borderColor: '#FCA5A5',
    borderRadius: 8,
    padding: 12,
    marginBottom: 16,
  },
  errorText: {
    color: '#991B1B',
    fontSize: 13,
    fontWeight: '600',
  },
  fieldGroup: {
    marginBottom: 18,
  },
  fieldLabel: {
    fontSize: 13,
    fontWeight: '700',
    color: Colors.text,
    marginBottom: 8,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  textInput: {
    backgroundColor: Colors.surface,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 15,
    color: Colors.text,
  },
  textArea: {
    minHeight: 90,
    textAlignVertical: 'top',
  },
  chipRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.surface,
    borderWidth: 1,
    borderColor: '#CBD5E1',
    borderRadius: 20,
    paddingHorizontal: 12,
    paddingVertical: 8,
    gap: 6,
  },
  chipSelected: {
    backgroundColor: '#E8F5E9',
    borderColor: Colors.brandGreen,
    borderWidth: 1.5,
  },
  chipIcon: {
    fontSize: 16,
  },
  chipText: {
    fontSize: 13,
    color: Colors.text,
    fontWeight: '500',
  },
  chipTextSelected: {
    color: Colors.brandGreen,
    fontWeight: '700',
  },
  twoColumnRow: {
    flexDirection: 'row',
    gap: 12,
  },
  unitRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  unitChip: {
    backgroundColor: Colors.surface,
    borderWidth: 1,
    borderColor: '#CBD5E1',
    borderRadius: 8,
    paddingVertical: 8,
    paddingHorizontal: 14,
  },
  unitChipSelected: {
    backgroundColor: Colors.brandGreen,
    borderColor: Colors.brandGreen,
  },
  unitChipText: {
    fontSize: 13,
    fontWeight: '600',
    color: Colors.text,
  },
  unitChipTextSelected: {
    color: '#FFFFFF',
  },
  presetRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  presetPill: {
    backgroundColor: Colors.surface,
    borderWidth: 1,
    borderColor: '#CBD5E1',
    borderRadius: 16,
    paddingHorizontal: 12,
    paddingVertical: 6,
  },
  presetPillSelected: {
    backgroundColor: '#E8F5E9',
    borderColor: Colors.brandGreen,
  },
  presetText: {
    fontSize: 12,
    color: '#4B5563',
  },
  presetTextSelected: {
    color: Colors.brandGreen,
    fontWeight: '700',
  },
  publishButton: {
    backgroundColor: Colors.brandGreen,
    borderRadius: 12,
    paddingVertical: 16,
    alignItems: 'center',
    marginTop: 10,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 3,
  },
  buttonDisabled: {
    opacity: 0.7,
  },
  publishButtonText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '700',
  },
});
