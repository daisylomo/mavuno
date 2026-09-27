import { Image } from 'expo-image';
import { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  useWindowDimensions,
  View,
} from 'react-native';

import {
  getCategories,
  getListing,
  getListings,
  listingImageUrl,
  type Category,
  type Listing,
} from '@/components/customer-catalog-api';

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'The catalog request failed. Try again.';
}

function Photo({ listing, style }: { listing: Listing; style: { width: number | `${number}%`; height: number } }) {
  const [failed, setFailed] = useState(false);
  const source = listingImageUrl(listing.images[0]?.object_key);
  useEffect(() => setFailed(false), [source]);
  return source && !failed ? (
    <Image
      source={{ uri: source }}
      style={style}
      contentFit="cover"
      accessibilityLabel={listing.images[0]?.alt_text || listing.title}
      onError={() => setFailed(true)}
    />
  ) : (
    <View style={[style, styles.photoUnavailable]}>
      <Text style={styles.photoUnavailableText}>Photo unavailable</Text>
    </View>
  );
}

function Price({ listing }: { listing: Listing }) {
  const amount = Number(listing.price_amount);
  const formatted = Number.isFinite(amount)
    ? `${listing.currency} ${amount.toLocaleString('en-KE', { maximumFractionDigits: 2 })}`
    : `${listing.currency} ${listing.price_amount}`;
  return <Text style={styles.price}>{formatted} / {listing.quantity_unit}</Text>;
}

export default function CustomerLiveCatalog({ baseUrl }: { baseUrl: string }) {
  const { width } = useWindowDimensions();
  const [categories, setCategories] = useState<Category[]>([]);
  const [categoryError, setCategoryError] = useState<string | null>(null);
  const [categoryRetry, setCategoryRetry] = useState(0);
  const [category, setCategory] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [items, setItems] = useState<Listing[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const [nextPage, setNextPage] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selected, setSelected] = useState<Listing | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [detailRetry, setDetailRetry] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setCategoryError(null);
    getCategories(baseUrl, controller.signal).then(setCategories).catch((error: unknown) => {
      if (!controller.signal.aborted) setCategoryError(errorMessage(error));
    });
    return () => controller.abort();
  }, [baseUrl, categoryRetry]);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search.trim()), 350);
    return () => clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    const controller = new AbortController();
    setListError(null);
    if (search.trim().length === 1) {
      setLoading(false);
      setLoadingMore(false);
      setItems([]);
      setNextPage(null);
      return () => controller.abort();
    }
    if (search.trim() !== debouncedSearch) {
      setLoading(true);
      return () => controller.abort();
    }
    if (cursor === null) {
      setLoading(true);
      setItems([]);
    } else {
      setLoadingMore(true);
    }
    getListings(baseUrl, { search: debouncedSearch, category, cursor: cursor ?? undefined }, controller.signal)
      .then((page) => {
        if (controller.signal.aborted) return;
        setItems((current) => cursor === null ? page.items : [
          ...current,
          ...page.items.filter((item) => !current.some((existing) => existing.id === item.id)),
        ]);
        setNextPage(page.next_cursor);
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setListError(errorMessage(error));
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoading(false);
          setLoadingMore(false);
        }
      });
    return () => controller.abort();
  }, [baseUrl, category, cursor, debouncedSearch, retry, search]);

  useEffect(() => {
    if (selectedId === null) return;
    const controller = new AbortController();
    setSelected(null);
    setDetailError(null);
    getListing(baseUrl, selectedId, controller.signal)
      .then((listing) => { if (!controller.signal.aborted) setSelected(listing); })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setDetailError(errorMessage(error));
      });
    return () => controller.abort();
  }, [baseUrl, selectedId, detailRetry]);

  function changeFilter(nextCategory: string | null) {
    setItems([]);
    setNextPage(null);
    setCursor(null);
    setCategory(nextCategory);
  }

  function changeSearch(value: string) {
    setItems([]);
    setNextPage(null);
    setCursor(null);
    setSearch(value);
  }

  return (
    <View style={styles.page}>
      <ScrollView contentContainerStyle={styles.scrollContent} keyboardShouldPersistTaps="handled">
        <View style={styles.content}>
          <View style={styles.topRow}>
            <Text style={styles.liveBadge}>LIVE CATALOG</Text>
          </View>
          <View style={styles.hero}>
            <Text style={styles.heroTitle}>Welcome to the Customer Marketplace</Text>
            <Text style={styles.heroSubtitle}>Browse fresh produce from local farmers</Text>
          </View>
          <Text style={styles.disclaimer}>Live listings from the API. Sign-in, cart and checkout are not connected yet.</Text>
          <TextInput
            accessibilityLabel="Search listings"
            placeholder="Search produce (at least 2 letters)..."
            placeholderTextColor="#71869A"
            value={search}
            onChangeText={changeSearch}
            style={styles.search}
            returnKeyType="search"
          />
          {categoryError && (
            <View style={styles.message}>
              <Text style={styles.error}>{categoryError}</Text>
              <Pressable accessibilityRole="button" onPress={() => setCategoryRetry((value) => value + 1)}>
                <Text style={styles.link}>Retry categories</Text>
              </Pressable>
            </View>
          )}
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.categories}>
            {[{ id: 'all', name: 'All', slug: '' }, ...categories].map((option) => (
              <Pressable
                key={option.id}
                accessibilityRole="button"
                accessibilityState={{ selected: category === (option.slug || null) }}
                onPress={() => changeFilter(option.slug || null)}
                style={[styles.categoryChip, category === (option.slug || null) && styles.activeChip]}
              >
                <Text style={[styles.categoryText, category === (option.slug || null) && styles.activeChipText]}>{option.name}</Text>
              </Pressable>
            ))}
          </ScrollView>
          <Text style={styles.sectionTitle}>Available listings</Text>
          {search.trim().length === 1 ? (
            <Text style={styles.muted}>Type one more letter to search.</Text>
          ) : loading ? (
            <ActivityIndicator accessibilityLabel="Loading listings" color="#2196F3" style={styles.loader} />
          ) : listError && !items.length ? (
            <View style={styles.message}>
              <Text style={styles.error}>{listError}</Text>
              <Pressable accessibilityRole="button" onPress={() => setRetry((value) => value + 1)}>
                <Text style={styles.link}>Retry listings</Text>
              </Pressable>
            </View>
          ) : items.length === 0 ? (
            <Text style={styles.muted}>No active listings match your search.</Text>
          ) : (
            <View style={styles.grid}>
              {items.map((listing) => (
                <Pressable
                  key={listing.id}
                  accessibilityRole="button"
                  accessibilityLabel={`View ${listing.title} details`}
                  onPress={() => setSelectedId(listing.id)}
                  style={[styles.card, { width: width >= 680 ? '48%' : '100%' }]}
                >
                  <Photo listing={listing} style={styles.cardPhoto} />
                  <View style={styles.cardInfo}>
                    <Text style={styles.categoryLabel}>{listing.category_slug.replace(/-/g, ' ').toUpperCase()}</Text>
                    <Text style={styles.productName}>{listing.title}</Text>
                    <Text style={styles.muted}>{listing.product_name}</Text>
                    <Price listing={listing} />
                    <Text style={styles.muted}>{listing.available_quantity} {listing.quantity_unit} available</Text>
                  </View>
                </Pressable>
              ))}
            </View>
          )}
          {listError && items.length > 0 && (
            <View style={styles.message}>
              <Text style={styles.error}>{listError}</Text>
              <Pressable accessibilityRole="button" onPress={() => setRetry((value) => value + 1)}>
                <Text style={styles.link}>Retry page</Text>
              </Pressable>
            </View>
          )}
          {nextPage && !loading && !loadingMore && !listError && (
            <Pressable accessibilityRole="button" onPress={() => setCursor(nextPage)} style={styles.loadMore}>
              <Text style={styles.loadMoreText}>Load more listings</Text>
            </Pressable>
          )}
          {loadingMore && <ActivityIndicator accessibilityLabel="Loading more listings" color="#2196F3" style={styles.loader} />}
        </View>
      </ScrollView>

      <Modal visible={selectedId !== null} transparent animationType="fade" onRequestClose={() => setSelectedId(null)}>
        <View style={styles.modalBackdrop}>
          <View style={styles.modalCard}>
            <Pressable accessibilityRole="button" accessibilityLabel="Close listing details" onPress={() => setSelectedId(null)}>
              <Text style={styles.close}>Close</Text>
            </Pressable>
            {detailError ? (
              <View style={styles.message}>
                <Text style={styles.error}>{detailError}</Text>
                <Pressable accessibilityRole="button" onPress={() => setDetailRetry((value) => value + 1)}>
                  <Text style={styles.link}>Retry details</Text>
                </Pressable>
              </View>
            ) : selected ? (
              <>
                <Photo listing={selected} style={styles.detailPhoto} />
                <Text style={styles.categoryLabel}>{selected.category_slug.replace(/-/g, ' ').toUpperCase()}</Text>
                <Text style={styles.heroTitle}>{selected.title}</Text>
                <Text style={styles.muted}>{selected.product_name}</Text>
                <Text style={styles.description}>{selected.description || 'No description provided.'}</Text>
                <Price listing={selected} />
                <Text style={styles.muted}>{selected.available_quantity} {selected.quantity_unit} available</Text>
                <Text style={styles.disclaimer}>Ordering this listing will be available after buyer sign-in and cart integration.</Text>
              </>
            ) : (
              <ActivityIndicator accessibilityLabel="Loading listing details" color="#2196F3" style={styles.loader} />
            )}
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  page: { flex: 1, backgroundColor: '#F5F9FC' },
  scrollContent: { flexGrow: 1, paddingHorizontal: 20, paddingBottom: 64 },
  content: { width: '100%', maxWidth: 1040, alignSelf: 'center' },
  topRow: { flexDirection: 'row', justifyContent: 'flex-end', alignItems: 'center', paddingVertical: 24 },
  liveBadge: { color: '#1164A7', backgroundColor: '#E1F1FE', borderRadius: 15, overflow: 'hidden', padding: 8, fontSize: 11, fontWeight: '800' },
  hero: { backgroundColor: '#DCEFFE', borderRadius: 24, padding: 30, marginBottom: 14 },
  heroTitle: { color: '#153C59', fontSize: 28, fontWeight: '800', marginBottom: 10 },
  heroSubtitle: { color: '#3B6077', fontSize: 16 },
  disclaimer: { color: '#456276', fontSize: 14, marginBottom: 18, marginTop: 6 },
  search: { backgroundColor: '#fff', borderRadius: 14, borderWidth: 1, borderColor: '#DCE6EE', paddingHorizontal: 18, paddingVertical: 14, fontSize: 16, color: '#17364D', marginBottom: 18 },
  categories: { gap: 10, paddingBottom: 26 },
  categoryChip: { backgroundColor: '#fff', borderColor: '#DCE6EE', borderWidth: 1, borderRadius: 20, paddingHorizontal: 18, paddingVertical: 10 },
  activeChip: { backgroundColor: '#2196F3', borderColor: '#2196F3' },
  categoryText: { color: '#456276', fontWeight: '600' },
  activeChipText: { color: '#fff' },
  sectionTitle: { color: '#17364D', fontSize: 22, fontWeight: '800', marginBottom: 16 },
  muted: { color: '#668096', fontSize: 14 },
  loader: { paddingVertical: 40 },
  message: { gap: 12, paddingVertical: 25 },
  error: { color: '#A4262C', fontSize: 15 },
  link: { color: '#1164A7', fontWeight: '700', paddingVertical: 8 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', gap: 16 },
  card: { backgroundColor: '#fff', borderRadius: 20, overflow: 'hidden', borderWidth: 1, borderColor: '#E5EDF3' },
  cardPhoto: { width: '100%', height: 170 },
  cardInfo: { padding: 18, gap: 6 },
  categoryLabel: { color: '#27865B', letterSpacing: 1, fontSize: 11, fontWeight: '800' },
  productName: { fontSize: 18, fontWeight: '700', color: '#17364D' },
  price: { fontSize: 16, fontWeight: '800', color: '#153C59', marginTop: 8 },
  photoUnavailable: { backgroundColor: '#E8EFF4', alignItems: 'center', justifyContent: 'center' },
  photoUnavailableText: { color: '#456276', fontWeight: '600' },
  loadMore: { backgroundColor: '#E1F1FE', borderRadius: 12, padding: 14, alignItems: 'center', marginTop: 22 },
  loadMoreText: { color: '#1164A7', fontWeight: '800' },
  modalBackdrop: { flex: 1, backgroundColor: 'rgba(13, 35, 52, 0.6)', justifyContent: 'center', alignItems: 'center', padding: 20 },
  modalCard: { width: '100%', maxWidth: 440, backgroundColor: '#fff', borderRadius: 22, padding: 24 },
  close: { color: '#1164A7', fontWeight: '700', alignSelf: 'flex-end', padding: 8, marginBottom: 10 },
  detailPhoto: { width: '100%', height: 180 },
  description: { color: '#456276', fontSize: 15, lineHeight: 23, marginVertical: 18 },
});
