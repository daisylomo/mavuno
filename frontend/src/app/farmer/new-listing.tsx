import React, { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Image,
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
import * as ImagePicker from 'expo-image-picker';
import { ImageManipulator, SaveFormat } from 'expo-image-manipulator';
import { Colors } from '@/constants/theme';
import {
  farmerService,
  ListingPhotoError,
  MAX_PHOTO_BYTES,
  type PhotoUpload,
} from '@/services/farmer-service';
import { base64Bytes, HARVEST_OPTIONS } from '@/components/listing-details';
import { ProduceCategory, ProduceUnit } from '@/types/farmer';
import { apiBaseUrl } from '@/components/customer-catalog-api';

const CATEGORIES: { label: ProduceCategory; icon: string }[] = [
  { label: 'Vegetables', icon: '🥬' },
  { label: 'Fruits', icon: '🥭' },
  { label: 'Grains & Cereals', icon: '🌽' },
  { label: 'Tubers & Roots', icon: '🥔' },
  { label: 'Dairy & Poultry', icon: '🥛' },
];

const UNITS: ProduceUnit[] = ['kg', 'crate', 'bunch', 'bag', 'piece'];

const PRODUCE_PRESETS = [
  { key: 'tomatoes', label: 'Tomatoes', source: require('@/assets/products/tomatoes.jpg'), icon: '🍅' },
  { key: 'spinach', label: 'Sukuma / Spinach', source: require('@/assets/products/spinach.jpg'), icon: '🥬' },
  { key: 'avocados', label: 'Hass Avocados', source: require('@/assets/products/avocados.jpg'), icon: '🥑' },
  { key: 'carrots', label: 'Fresh Carrots', source: require('@/assets/products/carrots.jpg'), icon: '🥕' },
  { key: 'mangoes', label: 'Sweet Mangoes', source: require('@/assets/products/mangoes.jpg'), icon: '🥭' },
  { key: 'bananas', label: 'Bananas', source: require('@/assets/products/bananas.jpg'), icon: '🍌' },
  { key: 'potatoes', label: 'Potatoes', source: require('@/assets/products/potatoes.jpg'), icon: '🥔' },
  { key: 'honey', label: 'Local Honey', source: require('@/assets/products/honey.jpg'), icon: '🍯' },
];

export default function NewListingScreen() {
  const router = useRouter();

  const [title, setTitle] = useState('');
  const [category, setCategory] = useState<ProduceCategory>('Vegetables');
  const [price, setPrice] = useState('');
  const [quantity, setQuantity] = useState('');
  const [unit, setUnit] = useState<ProduceUnit>('kg');
  const [harvestDate, setHarvestDate] = useState<string>(HARVEST_OPTIONS[0]);
  const [description, setDescription] = useState('');
  const [imageSource, setImageSource] = useState<any | null>(null);
  const [imageUrlValue, setImageUrlValue] = useState<string | null>(null);
  const [photo, setPhoto] = useState<PhotoUpload | null>(null);
  const [preparingPhoto, setPreparingPhoto] = useState(false);
  const [products, setProducts] = useState<Array<{ id: string; name: string; default_unit: ProduceUnit }>>([]);
  const [productId, setProductId] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    const base = apiBaseUrl();
    if (!base) return;
    fetch(`${base}/catalog/products`).then(async (response) => {
      if (!response.ok) throw new Error('Could not load produce types.');
      return response.json();
    }).then((data) => setProducts(data)).catch((cause: unknown) => {
      setError(cause instanceof Error ? cause.message : 'Could not load produce types.');
    });
  }, []);

  // The farmer's own photo is resized on the device (to about 1280px, JPEG) so it uploads
  // quickly on mobile data and stays under the server's limit.
  const preparePhoto = async (uri: string) => {
    setPreparingPhoto(true);
    try {
      const rendered = await ImageManipulator.manipulate(uri).resize({ width: 1280 }).renderAsync();
      const saved = await rendered.saveAsync({ compress: 0.7, format: SaveFormat.JPEG, base64: true });
      rendered.release();
      if (!saved.base64) throw new Error('The photo could not be read.');
      if (base64Bytes(saved.base64) > MAX_PHOTO_BYTES) {
        throw new Error('That photo is still too large after resizing. Try cropping it.');
      }
      setPhoto({ contentType: 'image/jpeg', base64: saved.base64 });
      setImageSource({ uri: saved.uri });
      setImageUrlValue(null);
      setError('');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'The photo could not be prepared.');
    } finally {
      setPreparingPhoto(false);
    }
  };

  const pickPhoto = async (fromCamera: boolean) => {
    const permission = fromCamera
      ? await ImagePicker.requestCameraPermissionsAsync()
      : await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) {
      setError(fromCamera
        ? 'Allow camera access in your phone settings to take a photo.'
        : 'Allow photo access in your phone settings to choose a photo.');
      return;
    }
    const options: ImagePicker.ImagePickerOptions = {
      mediaTypes: ['images'],
      allowsEditing: true,
      aspect: [4, 3],
      quality: 1,
    };
    const result = fromCamera
      ? await ImagePicker.launchCameraAsync(options)
      : await ImagePicker.launchImageLibraryAsync(options);
    if (result.canceled || !result.assets.length) return;
    await preparePhoto(result.assets[0].uri);
  };

  const handlePickImage = () => {
    if (Platform.OS === 'web') {
      pickPhoto(false);
      return;
    }
    Alert.alert('Add a photo of your produce', 'Buyers trust listings with the farmer\'s own photo.', [
      { text: 'Take photo', onPress: () => { pickPhoto(true); } },
      { text: 'Choose from gallery', onPress: () => { pickPhoto(false); } },
      { text: 'Cancel', style: 'cancel' },
    ]);
  };

  const handleSave = async () => {
    if (!title.trim()) {
      setError('Please enter the produce name');
      return;
    }
    if (apiBaseUrl() && !productId) {
      setError('Select a produce type before publishing.');
      return;
    }
    const numPrice = Number(price.trim());
    if (!Number.isFinite(numPrice) || numPrice <= 0) {
      setError('Please enter a valid price per unit');
      return;
    }
    if (apiBaseUrl() && !Number.isInteger(numPrice)) {
      setError('Enter the price in whole shillings (M-PESA cannot charge cents).');
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
        productId: productId || undefined,
        category,
        price: numPrice,
        quantity: numQuantity,
        unit,
        imageUrl: photo ? undefined : imageUrlValue || undefined,
        harvestDate,
        // Only what the farmer wrote. An empty description stays empty rather than claiming
        // anything (such as organic growing) on the farmer's behalf.
        description: description.trim(),
        status: numQuantity <= 10 ? 'low_stock' : 'active',
      }, photo ?? undefined);

      router.back();
    } catch (err: any) {
      if (err instanceof ListingPhotoError) {
        Alert.alert('Listing published', err.message);
        router.back();
        return;
      }
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
        {apiBaseUrl() && (
          <View style={styles.fieldGroup}>
            <Text style={styles.fieldLabel}>Produce type *</Text>
            <View style={styles.chipRow}>
              {products.map((product) => (
                <TouchableOpacity key={product.id}
                  style={[styles.chip, productId === product.id && styles.chipSelected]}
                  onPress={() => { setProductId(product.id); setUnit(product.default_unit); }}>
                  <Text style={styles.chipText}>{product.name}</Text>
                </TouchableOpacity>
              ))}
            </View>
            {products.length === 0 && <Text>No produce types are available yet. An administrator must add them.</Text>}
          </View>
        )}
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

        {/* Produce Photo Section */}
        <View style={styles.fieldGroup}>
          <Text style={styles.fieldLabel}>Produce Photo (Optional)</Text>
          {imageSource ? (
            <View style={styles.previewContainer}>
              <Image source={imageSource} style={styles.previewImage} />
              <View style={styles.previewOverlay}>
                <TouchableOpacity
                  style={styles.previewActionBtn}
                  onPress={handlePickImage}
                  activeOpacity={0.8}>
                  <Text style={styles.previewActionText}>🔄 Change</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[styles.previewActionBtn, styles.previewRemoveBtn]}
                  onPress={() => {
                    setImageSource(null);
                    setImageUrlValue(null);
                    setPhoto(null);
                  }}
                  activeOpacity={0.8}>
                  <Text style={styles.previewRemoveText}>✕ Remove</Text>
                </TouchableOpacity>
              </View>
            </View>
          ) : (
            <View>
              <TouchableOpacity
                style={styles.uploadCard}
                onPress={handlePickImage}
                activeOpacity={0.8}>
                {preparingPhoto ? <ActivityIndicator color={Colors.brandGreen} /> : <>
                  <Text style={styles.uploadCardIcon}>📷</Text>
                  <Text style={styles.uploadCardTitle}>Add a photo of your produce</Text>
                  <Text style={styles.uploadCardSub}>Take one now or choose from your gallery</Text>
                </>}
              </TouchableOpacity>

              <Text style={styles.presetHeading}>
                No photo yet? Use an illustration (buyers are told it is not your own photo):
              </Text>
              <View style={styles.presetChipRow}>
                {PRODUCE_PRESETS.map((preset) => (
                  <TouchableOpacity
                    key={preset.label}
                    style={styles.presetChip}
                    onPress={() => {
                      setImageSource(preset.source);
                      setImageUrlValue(`preset:${preset.key}`);
                      setPhoto(null);
                    }}
                    activeOpacity={0.75}>
                    <Text style={styles.presetChipIcon}>{preset.icon}</Text>
                    <Text style={styles.presetChipText}>{preset.label}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>
          )}
        </View>

        {/* Category Selector */}
        {!apiBaseUrl() && <View style={styles.fieldGroup}>
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
        </View>}

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
            {HARVEST_OPTIONS.map((preset) => {
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
            placeholder="Optional: how it was grown, quality, variety, minimum order..."
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
  uploadCard: {
    backgroundColor: '#F8FAFC',
    borderWidth: 2,
    borderColor: '#CBD5E1',
    borderStyle: 'dashed',
    borderRadius: 14,
    paddingVertical: 22,
    paddingHorizontal: 16,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 12,
  },
  uploadCardIcon: {
    fontSize: 32,
    marginBottom: 6,
  },
  uploadCardTitle: {
    fontSize: 15,
    fontWeight: '700',
    color: Colors.brandGreen,
  },
  uploadCardSub: {
    fontSize: 12,
    color: '#64748B',
    marginTop: 2,
  },
  previewContainer: {
    borderRadius: 14,
    overflow: 'hidden',
    backgroundColor: '#F1F5F9',
    borderWidth: 1,
    borderColor: '#E2E8F0',
    position: 'relative',
  },
  previewImage: {
    width: '100%',
    height: 200,
    resizeMode: 'cover',
  },
  previewOverlay: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    gap: 8,
    padding: 10,
    backgroundColor: 'rgba(15, 23, 42, 0.75)',
  },
  previewActionBtn: {
    backgroundColor: 'rgba(255, 255, 255, 0.25)',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 8,
  },
  previewActionText: {
    color: '#FFFFFF',
    fontSize: 12,
    fontWeight: '700',
  },
  previewRemoveBtn: {
    backgroundColor: '#DC2626',
  },
  previewRemoveText: {
    color: '#FFFFFF',
    fontSize: 12,
    fontWeight: '700',
  },
  presetHeading: {
    fontSize: 12,
    fontWeight: '600',
    color: '#64748B',
    marginBottom: 8,
  },
  presetChipRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
  },
  presetChip: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.surface,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    borderRadius: 16,
    paddingHorizontal: 10,
    paddingVertical: 6,
    gap: 4,
  },
  presetChipIcon: {
    fontSize: 14,
  },
  presetChipText: {
    fontSize: 12,
    color: Colors.text,
    fontWeight: '500',
  },
});
