import React, { useState } from 'react';
import { FlatList, Pressable, StyleSheet, Text, TextInput, useWindowDimensions, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Colors, Typography } from '../../constants/config';
import {
  PreviewEmptyState, PreviewIconButton, PreviewScreen, PreviewSheet, PreviewTabs,
} from '../../components/ServicePreview';

const SAMPLE_PRODUCTS = [
  { id: 'feed', name: 'Feed pellets', category: 'Feed', format: 'Bag', icon: 'nutrition-outline',
    color: '#BEE3CA', ink: '#195B3B', description: 'Pelleted livestock feed.', material: 'Composition not specified' },
  { id: 'hay', name: 'Hay bale', category: 'Feed', format: 'Bale', icon: 'leaf-outline',
    color: '#E1DCA8', ink: '#565522', description: 'Baled forage for livestock.', material: 'Variety not specified' },
  { id: 'trough', name: 'Water trough', category: 'Equipment', format: 'Single unit', icon: 'water-outline',
    color: '#BDDCE9', ink: '#24586B', description: 'A trough for a livestock watering area.', material: 'Polyethylene' },
  { id: 'tags', name: 'Ear tags', category: 'Equipment', format: 'Set', icon: 'pricetags-outline',
    color: '#F0DDA3', ink: '#6B5520', description: 'Visual identification tags.', material: 'Flexible plastic' },
  { id: 'brush', name: 'Grooming brush', category: 'Care', format: 'Single unit', icon: 'brush-outline',
    color: '#DDBFCC', ink: '#683B50', description: 'A handheld livestock grooming brush.', material: 'Wood and synthetic bristles' },
  { id: 'bucket', name: 'Feed bucket', category: 'Equipment', format: 'Single unit', icon: 'basket-outline',
    color: '#CCD9D4', ink: '#3C5C50', description: 'A bucket for daily feed handling.', material: 'Polyethylene' },
] as const;
type Product = typeof SAMPLE_PRODUCTS[number];
const CATEGORIES = [
  { value: 'All', label: 'All' }, { value: 'Feed', label: 'Feed' },
  { value: 'Equipment', label: 'Equipment' }, { value: 'Care', label: 'Care' },
] as const;
type Category = typeof CATEGORIES[number]['value'];

function ProductVisual({ product }: { product: Product }) {
  return (
    <View style={[styles.productVisual, { backgroundColor: product.color }]}>
      <Ionicons name={product.icon} size={56} color={product.ink} />
      <Text style={[styles.visualLabel, { color: product.ink }]}>Sample item</Text>
    </View>
  );
}

function MarketplaceWorkspace() {
  const insets = useSafeAreaInsets();
  const { width, fontScale } = useWindowDimensions();
  const columns = width < 360 || fontScale > 1.3 ? 1 : width >= 720 ? 3 : 2;
  const [category, setCategory] = useState<Category>('All');
  const [search, setSearch] = useState('');
  const [saved, setSaved] = useState<string[]>([]);
  const [savedOnly, setSavedOnly] = useState(false);
  const [selected, setSelected] = useState<Product | null>(null);
  const query = search.trim().toLowerCase();
  const products = SAMPLE_PRODUCTS.filter((product) =>
    (category === 'All' || product.category === category) &&
    (!savedOnly || saved.includes(product.id)) &&
    `${product.name} ${product.category} ${product.description}`.toLowerCase().includes(query));

  const toggleSaved = (id: string) => setSaved((current) =>
    current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);

  return (
    <View style={styles.root}>
      <View style={styles.searchBand}>
        <View style={styles.search}>
          <Ionicons name="search-outline" size={20} color={Colors.text.muted} />
          <TextInput accessibilityLabel="Search sample products" value={search} onChangeText={setSearch}
            placeholder="Search products" placeholderTextColor={Colors.text.muted}
            autoCorrect={false} returnKeyType="search" maxLength={100} style={styles.searchInput} />
          {!!search && <PreviewIconButton icon="close-outline" label="Clear search" onPress={() => setSearch('')} />}
        </View>
        <PreviewIconButton icon={savedOnly ? 'heart' : 'heart-outline'} label="Show saved items"
          selected={savedOnly} onPress={() => setSavedOnly((current) => !current)} />
      </View>
      <PreviewTabs options={CATEGORIES} value={category} onChange={setCategory} />
      <View style={styles.resultHeading}>
        <Text style={styles.sectionTitle}>{savedOnly ? 'Saved samples' : 'Sample catalog'}</Text>
        <Text style={styles.secondary}>{products.length} items</Text>
      </View>
      <FlatList key={columns} data={products} numColumns={columns} keyExtractor={(item) => item.id}
        keyboardShouldPersistTaps="handled" keyboardDismissMode="on-drag"
        style={styles.list} columnWrapperStyle={columns > 1 ? styles.gridRow : undefined}
        contentContainerStyle={[styles.grid, { paddingBottom: insets.bottom + 24 }]}
        ListEmptyComponent={<PreviewEmptyState icon={savedOnly ? 'heart-outline' : 'search-outline'}
          title={savedOnly ? 'No saved items match' : 'No matching products'} detail="Sample catalog only." />}
        renderItem={({ item }) => (
          <View style={[styles.product, { maxWidth: `${100 / columns}%` }]}>
            <Pressable accessibilityRole="button" accessibilityLabel={`View ${item.name}`} onPress={() => setSelected(item)}>
              <ProductVisual product={item} />
              <View style={styles.productInfo}>
                <Text style={styles.category}>{item.category}</Text>
                <Text style={styles.productName}>{item.name}</Text>
                <Text style={styles.secondary}>{item.format}</Text>
              </View>
            </Pressable>
            <View style={styles.productFooter}>
              <Text style={styles.availability}>Not for sale</Text>
              <PreviewIconButton icon={saved.includes(item.id) ? 'heart' : 'heart-outline'}
                label={`Save ${item.name}`} selected={saved.includes(item.id)} onPress={() => toggleSaved(item.id)} />
            </View>
          </View>
        )} />
      {selected && <PreviewSheet title={selected.name} onClose={() => setSelected(null)}>
        <ProductVisual product={selected} />
        <View style={styles.detailHeading}>
          <View style={styles.flex}>
            <Text style={styles.category}>{selected.category} / Sample item</Text>
            <Text style={styles.detailTitle}>{selected.name}</Text>
          </View>
          <PreviewIconButton icon={saved.includes(selected.id) ? 'heart' : 'heart-outline'}
            label={`Save ${selected.name}`} selected={saved.includes(selected.id)} onPress={() => toggleSaved(selected.id)} />
        </View>
        <Text style={styles.description}>{selected.description}</Text>
        <View style={styles.spec}><Text style={styles.secondary}>Format</Text><Text style={styles.specValue}>{selected.format}</Text></View>
        <View style={styles.spec}><Text style={styles.secondary}>Material</Text><Text style={styles.specValue}>{selected.material}</Text></View>
        <View style={styles.spec}><Text style={styles.secondary}>Seller / Price</Text><Text style={styles.specValue}>Not available</Text></View>
        <Pressable accessibilityRole="button" accessibilityLabel="Ordering unavailable" accessibilityState={{ disabled: true }}
          disabled style={styles.orderButton}>
          <Ionicons name="lock-closed-outline" size={18} color={Colors.text.muted} />
          <Text style={styles.secondary}>Ordering unavailable</Text>
        </Pressable>
      </PreviewSheet>}
    </View>
  );
}

export default function MarketplaceScreen() {
  return <PreviewScreen title="Marketplace"><MarketplaceWorkspace /></PreviewScreen>;
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  flex: { flex: 1 },
  searchBand: { flexDirection: 'row', gap: 8, alignItems: 'center', padding: 16 },
  search: { flex: 1, minHeight: 46, flexDirection: 'row', alignItems: 'center', paddingLeft: 12,
    borderWidth: 1, borderColor: Colors.border.default, borderRadius: 8, backgroundColor: Colors.bg.input },
  searchInput: { flex: 1, minWidth: 0, padding: 10, fontSize: Typography.base, color: Colors.text.primary },
  resultHeading: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', gap: 8, padding: 16 },
  sectionTitle: { color: Colors.text.primary, fontSize: Typography.base, fontWeight: '600' },
  secondary: { color: Colors.text.secondary, fontSize: Typography.sm, lineHeight: 20 },
  list: { flex: 1 },
  grid: { flexGrow: 1, paddingHorizontal: 16, gap: 12, width: '100%', maxWidth: 1000, alignSelf: 'center' },
  gridRow: { gap: 12 },
  product: { flex: 1, minWidth: 0, borderRadius: 8, backgroundColor: Colors.bg.card,
    borderWidth: 1, borderColor: Colors.border.default, overflow: 'hidden' },
  productVisual: { height: 132, alignItems: 'center', justifyContent: 'center', gap: 10 },
  visualLabel: { fontSize: Typography.xs, fontWeight: '600' },
  productInfo: { padding: 12, gap: 4 },
  category: { fontSize: Typography.xs, color: Colors.text.secondary },
  productName: { fontSize: Typography.base, lineHeight: 21, fontWeight: '600', color: Colors.text.primary },
  productFooter: { marginTop: 'auto', paddingLeft: 12, paddingRight: 4, flexDirection: 'row', alignItems: 'center', gap: 4 },
  availability: { flex: 1, fontSize: Typography.xs, color: Colors.text.secondary },
  detailHeading: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  detailTitle: { fontSize: Typography.lg, lineHeight: 26, color: Colors.text.primary, fontWeight: '600', marginTop: 4 },
  description: { color: Colors.text.secondary, fontSize: Typography.base, lineHeight: 23 },
  spec: { flexDirection: 'row', justifyContent: 'space-between', gap: 16, paddingVertical: 12,
    borderBottomWidth: 1, borderBottomColor: Colors.border.default },
  specValue: { flex: 1, textAlign: 'right', fontSize: Typography.sm, lineHeight: 20, color: Colors.text.primary },
  orderButton: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'center',
    minHeight: 48, padding: 12, gap: 8, borderRadius: 8, backgroundColor: Colors.bg.elevated },
});
