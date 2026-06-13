-- SHOMER: Tablas para Dashboard, métricas y inventario pasivo
-- Ejecutar: sqlite3 /storage/db/network_monitor.db < migrate_shomer_tables.sql

-- Estado en tiempo real para el Dashboard
CREATE TABLE IF NOT EXISTS system_state (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Métricas de salud para gráficas (Servidor .205)
CREATE TABLE IF NOT EXISTS server_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cpu_usage REAL,
    ram_usage REAL,
    temperature REAL,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Inventario pasivo de huéspedes (Extraídos de tabla ARP)
CREATE TABLE IF NOT EXISTS devices_inventory (
    mac_address TEXT PRIMARY KEY,
    ip_address TEXT,
    hostname TEXT,
    last_seen TIMESTAMP,
    promoted INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_server_metrics_recorded ON server_metrics(recorded_at);
CREATE INDEX IF NOT EXISTS idx_devices_inventory_promoted ON devices_inventory(promoted);
