import { useMemo, useState } from 'react';
import { Image } from 'expo-image';
import { apiBaseUrl, imageBaseUrl, type ListingUnit } from '@/components/customer-catalog-api';
import CustomerLiveCatalog from '@/components/customer-live-catalog';
import {
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  useWindowDimensions,
  View,
} from 'react-native';

type Category = 'Vegetables' | 'Fruits' | 'Pantry';
type Product = {
  id: string;
  name: string;
  category: Category;
  price: number;
  unit: ListingUnit;
  farmer: string;
  description: string;
  stock: number;
  image: number;
};
type Screen = 'browse' | 'cart' | 'checkout' | 'complete';

const PRODUCTS: Product[] = [
  { id: 'tomatoes', name: 'Fresh Tomatoes', category: 'Vegetables', price: 120, unit: 'kg', farmer: 'Maua Farm', description: 'Ripe, hand-picked tomatoes for your everyday meals.', stock: 12, image: require('@/assets/products/tomatoes.jpg') },
  { id: 'spinach', name: 'Garden Spinach', category: 'Vegetables', price: 80, unit: 'bunch', farmer: 'Green Acres', description: 'Tender leafy greens harvested fresh from the garden.', stock: 15, image: require('@/assets/products/spinach.jpg') },
  { id: 'mangoes', name: 'Sweet Mangoes', category: 'Fruits', price: 180, unit: 'kg', farmer: 'Sunrise Orchard', description: 'Juicy seasonal mangoes, perfect for snacking.', stock: 8, image: require('@/assets/products/mangoes.jpg') },
  { id: 'bananas', name: 'Ripe Bananas', category: 'Fruits', price: 100, unit: 'bunch', farmer: 'Maua Farm', description: 'Naturally ripened bananas from a local grower.', stock: 10, image: require('@/assets/products/bananas.jpg') },
  { id: 'carrots', name: 'Crunchy Carrots', category: 'Vegetables', price: 90, unit: 'kg', farmer: 'Green Acres', description: 'Sweet, crisp carrots for salads and cooking.', stock: 14, image: require('@/assets/products/carrots.jpg') },
  { id: 'avocados', name: 'Creamy Avocados', category: 'Fruits', price: 75, unit: 'piece', farmer: 'Hilltop Harvest', description: 'Creamy avocados picked at just the right time. Sold individually.', stock: 18, image: require('@/assets/products/avocados.jpg') },
  { id: 'potatoes', name: 'Farm Potatoes', category: 'Vegetables', price: 110, unit: 'kg', farmer: 'Hilltop Harvest', description: 'Versatile potatoes, ready for your favorite recipes.', stock: 20, image: require('@/assets/products/potatoes.jpg') },
  { id: 'honey', name: 'Local Honey', category: 'Pantry', price: 450, unit: 'piece', farmer: 'Sunrise Orchard', description: 'Golden honey from local beekeepers. One jar per piece.', stock: 6, image: require('@/assets/products/honey.jpg') },
];

const CATEGORIES: Array<'All' | Category> = ['All', 'Vegetables', 'Fruits', 'Pantry'];
const formatPrice = (amount: number) => `KES ${amount.toLocaleString('en-KE')}`;

type ActionButtonProps = {
  label: string;
  onPress: () => void;
  secondary?: boolean;
  disabled?: boolean;
};

function ActionButton({ label, onPress, secondary = false, disabled = false }: ActionButtonProps) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled }}
      disabled={disabled}
      onPress={onPress}
      style={[styles.button, secondary && styles.secondaryButton, disabled && styles.disabledButton]}
    >
      <Text style={[styles.buttonText, secondary && styles.secondaryButtonText]}>{label}</Text>
    </Pressable>
  );
}

export default function CustomerDashboard() {
  let baseUrl: string | null;
  try {
    baseUrl = apiBaseUrl();
    if (baseUrl) imageBaseUrl();
  } catch (error) {
    return (
      <View style={styles.emptyState}>
        <Text style={styles.pageTitle}>Catalog configuration error</Text>
        <Text style={styles.muted}>{error instanceof Error ? error.message : 'Invalid catalog configuration.'}</Text>
      </View>
    );
  }
  return baseUrl ? <CustomerLiveCatalog baseUrl={baseUrl} /> : <CustomerDemo />;
}

function CustomerDemo() {
  const { width } = useWindowDimensions();
  const [screen, setScreen] = useState<Screen>('browse');
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState<(typeof CATEGORIES)[number]>('All');
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null);
  const [cart, setCart] = useState<Record<string, number>>({});

  const filteredProducts = useMemo(() => {
    const query = search.trim().toLowerCase();
    return PRODUCTS.filter(
      (product) =>
        (category === 'All' || product.category === category) &&
        (!query || `${product.name} ${product.farmer} ${product.category}`.toLowerCase().includes(query)),
    );
  }, [category, search]);
  const cartItems = PRODUCTS.filter((product) => (cart[product.id] ?? 0) > 0);
  const cartCount = cartItems.reduce((count, product) => count + cart[product.id], 0);
  const total = cartItems.reduce((sum, product) => sum + product.price * cart[product.id], 0);

  function changeQuantity(product: Product, change: number) {
    setCart((current) => {
      const nextQuantity = Math.max(0, Math.min(product.stock, (current[product.id] ?? 0) + change));
      const next = { ...current };
      if (nextQuantity === 0) {
        delete next[product.id];
      } else {
        next[product.id] = nextQuantity;
      }
      return next;
    });
  }

  return (
    <View style={styles.page}>
      <ScrollView contentContainerStyle={styles.scrollContent} keyboardShouldPersistTaps="handled">
        <View style={styles.content}>
          <View style={styles.topRow}>
            {screen !== 'complete' && (
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={`View cart, ${cartCount} ${cartCount === 1 ? 'item' : 'items'}`}
                onPress={() => setScreen('cart')}
                style={styles.cartShortcut}
              >
                <Text style={styles.cartShortcutText}>Cart ({cartCount})</Text>
              </Pressable>
            )}
          </View>

          {screen === 'browse' && (
            <>
              <View style={styles.hero}>
                <Text style={styles.eyebrow}>FRESH FROM LOCAL FARMS</Text>
                <Text style={styles.heroTitle}>Welcome to the Customer Marketplace</Text>
                <Text style={styles.heroSubtitle}>Browse fresh produce from local farmers</Text>
              </View>
              <TextInput
                accessibilityLabel="Search products or farmers"
                placeholder="Search produce or farmers..."
                placeholderTextColor="#71869A"
                value={search}
                onChangeText={setSearch}
                style={styles.search}
                returnKeyType="search"
              />
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.categories}>
                {CATEGORIES.map((item) => (
                  <Pressable
                    key={item}
                    accessibilityRole="button"
                    accessibilityState={{ selected: category === item }}
                    onPress={() => setCategory(item)}
                    style={[styles.categoryChip, category === item && styles.activeChip]}
                  >
                    <Text style={[styles.categoryText, category === item && styles.activeChipText]}>{item}</Text>
                  </Pressable>
                ))}
              </ScrollView>
              <View style={styles.sectionHeader}>
                <Text style={styles.sectionTitle}>Fresh picks</Text>
                <Text style={styles.muted}>{filteredProducts.length} {filteredProducts.length === 1 ? 'product' : 'products'}</Text>
              </View>
              {filteredProducts.length === 0 ? (
                <View style={styles.emptyState}>
                  <Text style={styles.sectionTitle}>No products found</Text>
                  <Text style={styles.muted}>Try another search or category.</Text>
                  <ActionButton label="Clear filters" secondary onPress={() => { setSearch(''); setCategory('All'); }} />
                </View>
              ) : (
                <View style={styles.productGrid}>
                  {filteredProducts.map((product) => (
                    <View key={product.id} style={[styles.productCard, { width: width >= 680 ? '48%' : '100%' }]}>
                      <Pressable accessibilityRole="button" accessibilityLabel={`View ${product.name} details`} onPress={() => setSelectedProduct(product)}>
                        <Image source={product.image} style={styles.productImage} contentFit="cover" accessibilityLabel={product.name} />
                        <View style={styles.productInfo}>
                          <Text style={styles.productCategory}>{product.category.toUpperCase()}</Text>
                          <Text style={styles.productName}>{product.name}</Text>
                          <Text style={styles.muted}>From {product.farmer}</Text>
                        </View>
                      </Pressable>
                      <View style={styles.productFooter}>
                        <Text style={styles.price}>{formatPrice(product.price)} <Text style={styles.unit}>/ {product.unit}</Text></Text>
                        <Pressable
                          accessibilityRole="button"
                          accessibilityLabel={`Add ${product.name} to cart`}
                          accessibilityState={{ disabled: (cart[product.id] ?? 0) >= product.stock }}
                          disabled={(cart[product.id] ?? 0) >= product.stock}
                          onPress={() => changeQuantity(product, 1)}
                          style={styles.addButton}
                        >
                          <Text style={styles.addButtonText}>+ Add</Text>
                        </Pressable>
                      </View>
                    </View>
                  ))}
                </View>
              )}
            </>
          )}

          {screen === 'cart' && (
            <>
              <Text style={styles.pageTitle}>Your cart</Text>
              <Text style={styles.muted}>{cartCount} {cartCount === 1 ? 'item' : 'items'} from local farmers</Text>
              {cartItems.length === 0 ? (
                <View style={styles.emptyState}>
                  <Text style={styles.sectionTitle}>Your cart is empty</Text>
                  <Text style={styles.muted}>Explore the market and add something fresh.</Text>
                  <ActionButton label="Browse products" onPress={() => setScreen('browse')} />
                </View>
              ) : (
                <>
                  {cartItems.map((product) => (
                    <View key={product.id} style={styles.cartRow}>
                      <Image source={product.image} style={styles.cartImage} contentFit="cover" accessibilityLabel={product.name} />
                      <View style={styles.cartDetails}>
                        <Text style={styles.productName}>{product.name}</Text>
                        <Text style={styles.muted}>{formatPrice(product.price)} / {product.unit}</Text>
                        <View style={styles.quantityControls}>
                          <Pressable accessibilityRole="button" accessibilityLabel={`Remove one ${product.name}`} onPress={() => changeQuantity(product, -1)} style={styles.quantityButton}>
                            <Text style={styles.quantityText}>-</Text>
                          </Pressable>
                          <Text style={styles.quantityValue}>{cart[product.id]}</Text>
                          <Pressable accessibilityRole="button" accessibilityLabel={`Add one ${product.name}`} accessibilityState={{ disabled: cart[product.id] >= product.stock }} disabled={cart[product.id] >= product.stock} onPress={() => changeQuantity(product, 1)} style={styles.quantityButton}>
                            <Text style={styles.quantityText}>+</Text>
                          </Pressable>
                        </View>
                      </View>
                      <Text style={styles.price}>{formatPrice(product.price * cart[product.id])}</Text>
                    </View>
                  ))}
                  <View style={styles.summary}>
                    <Text style={styles.summaryLabel}>Subtotal</Text>
                    <Text style={styles.summaryAmount}>{formatPrice(total)}</Text>
                  </View>
                  <Text style={styles.note}>Demo prices only. Delivery and payment are not available.</Text>
                  <View style={styles.actions}>
                    <ActionButton label="Continue shopping" secondary onPress={() => setScreen('browse')} />
                    <ActionButton label="Review demo order" onPress={() => setScreen('checkout')} />
                  </View>
                </>
              )}
            </>
          )}

          {screen === 'checkout' && (
            <>
              <Text style={styles.pageTitle}>Review your order</Text>
              <Text style={styles.muted}>This is a preview. No payment or real order will be made.</Text>
              <View style={styles.reviewCard}>
                {cartItems.map((product) => (
                  <View key={product.id} style={styles.reviewRow}>
                    <View style={styles.reviewProduct}>
                      <Image source={product.image} style={styles.reviewImage} contentFit="cover" accessibilityLabel={product.name} />
                      <Text style={styles.reviewItem}>{product.name} x {cart[product.id]}</Text>
                    </View>
                    <Text style={styles.price}>{formatPrice(product.price * cart[product.id])}</Text>
                  </View>
                ))}
                <View style={styles.summary}>
                  <Text style={styles.summaryLabel}>Demo total</Text>
                  <Text style={styles.summaryAmount}>{formatPrice(total)}</Text>
                </View>
              </View>
              <View style={styles.actions}>
                <ActionButton label="Back to cart" secondary onPress={() => setScreen('cart')} />
                <ActionButton label="Place demo order" disabled={cartCount === 0} onPress={() => { setCart({}); setScreen('complete'); }} />
              </View>
            </>
          )}

          {screen === 'complete' && (
            <View style={styles.emptyState}>
              <Text style={styles.successMark}>✓</Text>
              <Text style={styles.pageTitle}>Demo order complete!</Text>
              <Text style={styles.muted}>This was a preview only. No order was sent and no payment was taken.</Text>
              <ActionButton label="Back to marketplace" onPress={() => setScreen('browse')} />
            </View>
          )}
        </View>
      </ScrollView>

      <Modal visible={selectedProduct !== null} transparent animationType="fade" onRequestClose={() => setSelectedProduct(null)}>
        <View style={styles.modalBackdrop}>
          {selectedProduct && (
            <View style={styles.modalCard}>
              <Pressable accessibilityRole="button" accessibilityLabel="Close product details" onPress={() => setSelectedProduct(null)} style={styles.closeButton}>
                <Text style={styles.closeText}>Close</Text>
              </Pressable>
              <Image source={selectedProduct.image} style={styles.detailImage} contentFit="cover" accessibilityLabel={selectedProduct.name} />
              <Text style={styles.productCategory}>{selectedProduct.category.toUpperCase()}</Text>
              <Text style={styles.pageTitle}>{selectedProduct.name}</Text>
              <Text style={styles.muted}>Grown by {selectedProduct.farmer}</Text>
              <Text style={styles.description}>{selectedProduct.description}</Text>
              <Text style={styles.price}>{formatPrice(selectedProduct.price)} / {selectedProduct.unit}</Text>
              <Text style={styles.note}>{selectedProduct.stock - (cart[selectedProduct.id] ?? 0)} available to add</Text>
              <ActionButton
                label="Add to cart"
                disabled={(cart[selectedProduct.id] ?? 0) >= selectedProduct.stock}
                onPress={() => { changeQuantity(selectedProduct, 1); setSelectedProduct(null); }}
              />
            </View>
          )}
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  page: { flex: 1, backgroundColor: '#F5F9FC' },
  scrollContent: { flexGrow: 1, paddingHorizontal: 20, paddingBottom: 64 },
  content: { width: '100%', maxWidth: 1040, alignSelf: 'center' },
  topRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'flex-end', paddingVertical: 24 },
  cartShortcut: { backgroundColor: '#E1F1FE', paddingHorizontal: 16, paddingVertical: 10, borderRadius: 20 },
  cartShortcutText: { color: '#1164A7', fontWeight: '700' },
  hero: { backgroundColor: '#DCEFFE', borderRadius: 24, padding: 30, marginBottom: 24 },
  eyebrow: { color: '#1570B4', fontWeight: '800', letterSpacing: 2, fontSize: 11, marginBottom: 12 },
  heroTitle: { color: '#153C59', fontSize: 30, fontWeight: '800', maxWidth: 520, marginBottom: 10 },
  heroSubtitle: { color: '#3B6077', fontSize: 16 },
  search: { backgroundColor: '#fff', borderRadius: 14, borderWidth: 1, borderColor: '#DCE6EE', paddingHorizontal: 18, paddingVertical: 14, fontSize: 16, color: '#17364D', marginBottom: 18 },
  categories: { gap: 10, paddingBottom: 26 },
  categoryChip: { backgroundColor: '#fff', borderColor: '#DCE6EE', borderWidth: 1, borderRadius: 20, paddingHorizontal: 18, paddingVertical: 10 },
  activeChip: { backgroundColor: '#2196F3', borderColor: '#2196F3' },
  categoryText: { color: '#456276', fontWeight: '600' },
  activeChipText: { color: '#fff' },
  sectionHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 },
  sectionTitle: { color: '#17364D', fontSize: 22, fontWeight: '800' },
  muted: { color: '#668096', fontSize: 14 },
  productGrid: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', gap: 16 },
  productCard: { backgroundColor: '#fff', borderRadius: 20, overflow: 'hidden', borderWidth: 1, borderColor: '#E5EDF3' },
  productImage: { width: '100%', height: 170, backgroundColor: '#E8EFF4' },
  productInfo: { paddingHorizontal: 18, paddingTop: 18 },
  productCategory: { color: '#27865B', letterSpacing: 1.4, fontSize: 11, fontWeight: '800', marginBottom: 5 },
  productName: { fontSize: 18, fontWeight: '700', color: '#17364D', marginBottom: 5 },
  productFooter: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 18, gap: 8 },
  price: { fontSize: 15, fontWeight: '800', color: '#153C59' },
  unit: { color: '#668096', fontWeight: '400', fontSize: 12 },
  addButton: { backgroundColor: '#E1F1FE', borderRadius: 12, paddingHorizontal: 15, paddingVertical: 10 },
  addButtonText: { color: '#1164A7', fontWeight: '800' },
  pageTitle: { color: '#17364D', fontSize: 28, fontWeight: '800', marginBottom: 8 },
  emptyState: { alignItems: 'center', gap: 16, paddingVertical: 80 },
  cartRow: { backgroundColor: '#fff', borderRadius: 16, padding: 16, marginTop: 16, flexDirection: 'row', alignItems: 'center', gap: 14, flexWrap: 'wrap' },
  cartImage: { width: 72, height: 72, borderRadius: 12, backgroundColor: '#E8EFF4' },
  cartDetails: { flex: 1, minWidth: 130 },
  quantityControls: { flexDirection: 'row', alignItems: 'center', gap: 14, marginTop: 12 },
  quantityButton: { backgroundColor: '#E1F1FE', width: 30, height: 30, alignItems: 'center', justifyContent: 'center', borderRadius: 8 },
  quantityText: { color: '#1164A7', fontSize: 18, fontWeight: '700' },
  quantityValue: { fontWeight: '700', color: '#17364D' },
  summary: { borderTopWidth: 1, borderColor: '#DCE6EE', flexDirection: 'row', justifyContent: 'space-between', paddingTop: 22, marginTop: 24 },
  summaryLabel: { color: '#456276', fontSize: 16, fontWeight: '600' },
  summaryAmount: { color: '#17364D', fontSize: 22, fontWeight: '800' },
  note: { color: '#668096', fontSize: 13, marginTop: 12 },
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginTop: 28 },
  button: { backgroundColor: '#2196F3', borderRadius: 12, paddingHorizontal: 22, paddingVertical: 14, alignItems: 'center', justifyContent: 'center', minHeight: 48 },
  buttonText: { color: '#fff', fontWeight: '800', fontSize: 15 },
  secondaryButton: { backgroundColor: '#E1F1FE' },
  secondaryButtonText: { color: '#1164A7' },
  disabledButton: { opacity: 0.5 },
  reviewCard: { backgroundColor: '#fff', borderRadius: 20, padding: 22, marginTop: 24 },
  reviewRow: { flexDirection: 'row', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12, paddingVertical: 10 },
  reviewProduct: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  reviewImage: { width: 36, height: 36, borderRadius: 8 },
  reviewItem: { color: '#17364D', fontSize: 15 },
  successMark: { fontSize: 56, color: '#27865B' },
  modalBackdrop: { flex: 1, backgroundColor: 'rgba(13, 35, 52, 0.6)', justifyContent: 'center', alignItems: 'center', padding: 20 },
  modalCard: { width: '100%', maxWidth: 440, backgroundColor: '#fff', borderRadius: 22, padding: 24 },
  closeButton: { alignSelf: 'flex-end', padding: 8 },
  closeText: { color: '#1164A7', fontWeight: '700' },
  detailImage: { width: '100%', height: 220, borderRadius: 16, marginBottom: 20, backgroundColor: '#E8EFF4' },
  description: { color: '#456276', fontSize: 15, lineHeight: 23, marginVertical: 18 },
});
