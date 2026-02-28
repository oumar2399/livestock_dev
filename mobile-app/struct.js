const fs = require("fs");
const path = require("path");

const structure = [
  "App.tsx",
  "src/types/index.ts",
  "src/constants/config.ts",
  "src/api/client.ts",
  "src/api/animals.ts",
  "src/api/telemetry.ts",
  "src/api/alerts.ts",
  "src/store/authStore.ts",
  "src/hooks/useAnimals.ts",
  "src/hooks/useTelemetry.ts",
  "src/hooks/useAlerts.ts",
  "src/components/ui.tsx",
  "src/utils/helpers.ts",
  "src/navigation/RootNavigator.tsx",
  "src/navigation/MainNavigator.tsx",
  "src/screens/LoginScreen.tsx",
  "src/screens/DashboardScreen.tsx",
  "src/screens/MapScreen.tsx",
  "src/screens/AnimalsListScreen.tsx",
  "src/screens/AnimalDetailScreen.tsx",
  "src/screens/AlertsListScreen.tsx",
  "src/screens/ProfileScreen.tsx",
];

structure.forEach(file => {
  const dir = path.dirname(file);
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(file, "");
});

console.log("Structure créée avec succès 🚀");