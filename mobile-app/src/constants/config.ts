// ─── Configuration Application ───────────────────────────────────────────────
// Modifier BASE_URL selon votre environnement de déploiement

export const Config = {
  // URL backend FastAPI
  // Développement local : adresse IP de votre machine sur le réseau WiFi
  // Production : URL de votre serveur (ex: https://api.votre-domaine.com)
  API_BASE_URL: 'http://192.168.1.100:8000/api/v1',

  // Timeouts (ms)
  REQUEST_TIMEOUT: 15_000,
  CONNECT_TIMEOUT: 10_000,

  // Polling intervalles (ms) - pour carte et dashboard temps réel
  MAP_REFRESH_INTERVAL: 10_000,     // 10s (cohérent avec M5Stack refresh)
  DASHBOARD_REFRESH_INTERVAL: 30_000,
  ALERTS_REFRESH_INTERVAL: 15_000,

  // Pagination
  ANIMALS_PAGE_SIZE: 50,
  ALERTS_LIMIT: 50,
  TELEMETRY_DEFAULT_HOURS: 24,

  // React Query - durée cache
  STALE_TIME_SHORT: 5_000,          // 5s pour données temps réel
  STALE_TIME_MEDIUM: 30_000,        // 30s pour listes
  STALE_TIME_LONG: 5 * 60_000,      // 5min pour données statiques

  // AsyncStorage keys
  STORAGE: {
    ACCESS_TOKEN: '@livestock/access_token',
    USER_PROFILE: '@livestock/user_profile',
    FARM_ID: '@livestock/farm_id',
  },
} as const;

// ─── Couleurs (Design System) ─────────────────────────────────────────────────

export const Colors = {
  // Backgrounds
  bg: {
    primary: '#0D1B2A',    // Fond principal - bleu nuit profond
    card: '#1B2A3B',       // Cartes
    elevated: '#243447',   // Éléments surélevés
    input: '#1A2535',      // Champs de saisie
  },

  // Couleur principale - vert herbe
  primary: '#27AE60',
  primaryLight: '#2ECC71',
  primaryDark: '#1E8449',
  primaryMuted: 'rgba(39,174,96,0.15)',

  // États animaux / alertes
  status: {
    healthy: '#27AE60',
    warning: '#F39C12',
    critical: '#E74C3C',
    offline: '#7F8C8D',
    unknown: '#95A5A6',
  },

  // Sévérité alertes
  severity: {
    info: '#3498DB',
    warning: '#F39C12',
    critical: '#E74C3C',
  },

  // États comportementaux
  behavior: {
    lying: '#8E44AD',      // violet - repos
    standing: '#3498DB',   // bleu - debout
    walking: '#27AE60',    // vert - marche
    running: '#E67E22',    // orange - course
  },

  // Statut animal
  animalStatus: {
    active: '#27AE60',
    sick: '#E74C3C',
    sold: '#95A5A6',
    deceased: '#7F8C8D',
  },

  // Batterie
  battery: {
    full: '#27AE60',       // >50%
    medium: '#F39C12',     // 20-50%
    low: '#E74C3C',        // <20%
  },

  // Texte
  text: {
    primary: '#ECF0F1',
    secondary: '#BDC3C7',
    muted: '#7F8C8D',
    disabled: '#4A5568',
  },

  // Bordures
  border: {
    default: 'rgba(255,255,255,0.08)',
    focused: 'rgba(39,174,96,0.5)',
  },

  // Overlays
  overlay: 'rgba(0,0,0,0.6)',
} as const;

// ─── Typographie ──────────────────────────────────────────────────────────────

export const Typography = {
  // Tailles
  xs: 11,
  sm: 13,
  base: 15,
  md: 17,
  lg: 20,
  xl: 24,
  '2xl': 30,
  '3xl': 36,

  // Line heights
  lineHeight: {
    tight: 1.2,
    normal: 1.5,
    relaxed: 1.75,
  },
} as const;

// ─── Espacement ───────────────────────────────────────────────────────────────

export const Spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  base: 16,
  lg: 20,
  xl: 24,
  '2xl': 32,
  '3xl': 48,
} as const;

// ─── Border Radius ────────────────────────────────────────────────────────────

export const Radius = {
  sm: 6,
  md: 10,
  lg: 14,
  xl: 20,
  full: 9999,
} as const;
