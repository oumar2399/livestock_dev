import React from 'react';
import { useRoute } from '@react-navigation/native';
import DrawerScreenBase, { ComingSoonPlaceholder } from './DrawerScreenBase';

const LABELS: Record<string, string> = {
  Chatbot: 'Assistant IA',
  Marketplace: 'Marketplace',
};

export default function ComingSoonScreen() {
  const route = useRoute();
  const label = LABELS[route.name] ?? route.name;
  return (
    <DrawerScreenBase title={label}>
      <ComingSoonPlaceholder feature={label} />
    </DrawerScreenBase>
  );
}