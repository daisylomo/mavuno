import React from 'react';
import { View, Text, StyleSheet, Pressable, Image } from 'react-native';
import { Colors } from '../constants/theme';

interface ProductCardProps {
  title: string;
  price: number;
  stock: string; // e.g., "50 kg available"
  imageUrl?: string;
  onPress: () => void;
}

export default function ProductCard({ title, price, stock, imageUrl, onPress }: ProductCardProps) {
  return (
    <Pressable style={styles.card} onPress={onPress}>
      {/* Image Placeholder */}
      <View style={styles.imageContainer}>
        {imageUrl ? (
          <Image source={{ uri: imageUrl }} style={styles.image} />
        ) : (
          <Text style={styles.imagePlaceholderText}>No Image</Text>
        )}
      </View>

      <View style={styles.detailsContainer}>
        <Text style={styles.title} numberOfLines={1}>{title}</Text>
        <Text style={styles.stock}>{stock}</Text>
        <Text style={styles.price}>KSh {price}</Text>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: Colors.surface,
    borderRadius: 12,
    overflow: 'hidden',
    marginBottom: 16,
    flexDirection: 'row',
    elevation: 2,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
  },
  imageContainer: {
    width: 100,
    height: 100,
    backgroundColor: '#E9ECEF',
    justifyContent: 'center',
    alignItems: 'center',
  },
  image: {
    width: '100%',
    height: '100%',
  },
  imagePlaceholderText: {
    color: Colors.textMuted,
    fontSize: 12,
  },
  detailsContainer: {
    flex: 1,
    padding: 12,
    justifyContent: 'center',
  },
  title: {
    fontSize: 16,
    fontWeight: 'bold',
    color: Colors.text,
    marginBottom: 4,
  },
  stock: {
    fontSize: 14,
    color: Colors.textMuted,
    marginBottom: 8,
  },
  price: {
    fontSize: 16,
    fontWeight: 'bold',
    color: Colors.brandGreen,
  },
});