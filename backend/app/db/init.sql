-- ============================================================
-- SCHEMA INITIAL - LIVESTOCK MONITORING
-- Version: 1.0
-- ============================================================

-- Table : Users (fermiers, propriétaires, vétérinaires)
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    name VARCHAR(255),
    role VARCHAR(50) DEFAULT 'farmer' CHECK (role IN ('farmer', 'owner', 'vet', 'admin')),
    phone VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_role ON users(role);

-- Table : Farms (fermes)
CREATE TABLE IF NOT EXISTS farms (
    id SERIAL PRIMARY KEY,
    owner_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    address TEXT,
    location GEOGRAPHY(POINT, 4326),  -- PostGIS: lat/lon WGS84
    size_hectares DECIMAL(10, 2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_farms_owner ON farms(owner_id);
CREATE INDEX idx_farms_location ON farms USING GIST(location);

-- Table : Animals (animaux)
CREATE TABLE IF NOT EXISTS animals (
    id SERIAL PRIMARY KEY,
    farm_id INTEGER REFERENCES farms(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    official_id VARCHAR(50) UNIQUE,  -- Numéro boucle oreille
    species VARCHAR(50) DEFAULT 'bovine',
    breed VARCHAR(100),
    sex CHAR(1) CHECK (sex IN ('M', 'F')),
    birth_date DATE,
    weight DECIMAL(6, 2),
    photo_url TEXT,
    assigned_device VARCHAR(50),  -- ID M5Stack
    status VARCHAR(50) DEFAULT 'active' CHECK (status IN ('active', 'sick', 'sold', 'deceased')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_animals_farm ON animals(farm_id);
CREATE INDEX idx_animals_device ON animals(assigned_device);
CREATE INDEX idx_animals_status ON animals(status);

-- Table : Telemetry (données capteurs - HYPERTABLE TimescaleDB)
CREATE TABLE IF NOT EXISTS telemetry (
    time TIMESTAMPTZ NOT NULL,
    animal_id INTEGER NOT NULL,
    device_id VARCHAR(50) NOT NULL,
    
    -- GPS
    location GEOGRAPHY(POINT, 4326),
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    altitude DECIMAL(7, 2),
    speed DECIMAL(5, 2),
    satellites INTEGER,
    
    -- Activité
    activity DECIMAL(5, 3),
    activity_state VARCHAR(20) CHECK (activity_state IN ('walking', 'standing', 'lying', 'running')),
    
    -- Santé
    temperature DECIMAL(4, 2),
    
    -- Système
    battery_level INTEGER CHECK (battery_level BETWEEN 0 AND 100),
    signal_strength INTEGER,
    
    PRIMARY KEY (animal_id, time)
);

-- Convertir en hypertable TimescaleDB (optimisation séries temporelles)
SELECT create_hypertable('telemetry', 'time', if_not_exists => TRUE);

-- Index optimisés
CREATE INDEX IF NOT EXISTS idx_telemetry_device ON telemetry(device_id, time DESC);
CREATE INDEX IF NOT EXISTS idx_telemetry_location ON telemetry USING GIST(location);

-- Politique compression (données > 7 jours compressées)
SELECT add_compression_policy('telemetry', INTERVAL '7 days', if_not_exists => TRUE);

-- Table : Alerts (alertes)
CREATE TABLE IF NOT EXISTS alerts (
    id SERIAL PRIMARY KEY,
    animal_id INTEGER REFERENCES animals(id) ON DELETE CASCADE,
    type VARCHAR(50) CHECK (type IN ('health', 'geofence', 'battery', 'offline', 'custom')),
    severity VARCHAR(20) CHECK (severity IN ('info', 'warning', 'critical')),
    title VARCHAR(255),
    message TEXT,
    triggered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    acknowledged_at TIMESTAMP,
    acknowledged_by INTEGER REFERENCES users(id),
    resolved_at TIMESTAMP,
    metadata JSONB
);

CREATE INDEX idx_alerts_animal ON alerts(animal_id, triggered_at DESC);
CREATE INDEX idx_alerts_severity ON alerts(severity, triggered_at DESC);
CREATE INDEX idx_alerts_unresolved ON alerts(resolved_at) WHERE resolved_at IS NULL;

-- Table : Geofences (zones géographiques)
CREATE TABLE IF NOT EXISTS geofences (
    id SERIAL PRIMARY KEY,
    farm_id INTEGER REFERENCES farms(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    polygon GEOGRAPHY(POLYGON, 4326),
    type VARCHAR(50) CHECK (type IN ('pasture', 'danger', 'building', 'water')),
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_geofences_farm ON geofences(farm_id);
CREATE INDEX idx_geofences_polygon ON geofences USING GIST(polygon);

-- Table : Devices (capteurs M5Stack)
CREATE TABLE IF NOT EXISTS devices (
    id VARCHAR(50) PRIMARY KEY,
    farm_id INTEGER REFERENCES farms(id),
    model VARCHAR(100),
    firmware_version VARCHAR(50),
    last_seen TIMESTAMP,
    battery_capacity INTEGER,
    status VARCHAR(50) DEFAULT 'active' CHECK (status IN ('active', 'maintenance', 'lost', 'retired')),
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_devices_farm ON devices(farm_id);
CREATE INDEX idx_devices_status ON devices(status);

-- ============================================================
-- DONNÉES DE TEST (optionnel - pour développement)
-- ============================================================

-- User test
INSERT INTO users (email, password_hash, name, role) 
VALUES ('test@example.com', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYqVqL2xQQy', 'Test User', 'farmer')
ON CONFLICT (email) DO NOTHING;
-- Mot de passe = "password123" (hashé avec bcrypt)

-- Farm test
INSERT INTO farms (owner_id, name, location)
SELECT 1, 'Ferme Test', ST_SetSRID(ST_MakePoint(2.3522, 48.8566), 4326)
WHERE EXISTS (SELECT 1 FROM users WHERE id = 1)
ON CONFLICT DO NOTHING;

-- Animal test
INSERT INTO animals (farm_id, name, official_id, assigned_device)
SELECT 1, 'Test Cow', 'FR001', 'M5-001'
WHERE EXISTS (SELECT 1 FROM farms WHERE id = 1)
ON CONFLICT (official_id) DO NOTHING;

-- ============================================================
-- VUES UTILES (requêtes fréquentes pré-calculées)
-- ============================================================

-- Vue : Dernière position de chaque animal
CREATE OR REPLACE VIEW animal_last_positions AS
SELECT DISTINCT ON (animal_id)
    a.id AS animal_id,
    a.name,
    a.status,
    t.time AS last_update,
    t.latitude,
    t.longitude,
    t.activity,
    t.battery_level
FROM animals a
LEFT JOIN telemetry t ON a.id = t.animal_id
ORDER BY animal_id, t.time DESC;