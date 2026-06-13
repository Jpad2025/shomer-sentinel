PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS devices (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT,
  device_type TEXT,
  ip_address TEXT UNIQUE,
  mac_address TEXT,
  brand TEXT,
  model TEXT,
  location TEXT,
  is_active INTEGER DEFAULT 1,
  is_guest INTEGER DEFAULT 0,
  status TEXT,
  created_at TEXT,
  updated_at TEXT,
  ssh_user TEXT,
  ssh_password TEXT,
  ssh_port INTEGER,
  snmp_community TEXT,
  reboot_method TEXT,
  reboot_command TEXT,
  last_reboot_at TEXT
);

CREATE TABLE IF NOT EXISTS device_status (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  device_id INTEGER NOT NULL,
  status TEXT,
  last_check TEXT,
  response_time REAL,
  uptime_percentage REAL,
  FOREIGN KEY(device_id) REFERENCES devices(id)
);

CREATE TABLE IF NOT EXISTS events_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  device_id INTEGER NOT NULL,
  event_type TEXT,
  description TEXT,
  severity TEXT,
  created_at TEXT,
  timestamp TEXT,
  FOREIGN KEY(device_id) REFERENCES devices(id)
);

CREATE TABLE IF NOT EXISTS discovered_devices (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ip_address    TEXT NOT NULL UNIQUE,
  mac_address   TEXT,
  vendor        TEXT,
  hostname      TEXT,
  open_ports    TEXT,
  inferred_type TEXT,
  status        TEXT,
  source        TEXT,
  first_seen    TEXT,
  last_seen     TEXT
);

CREATE INDEX IF NOT EXISTS idx_device_status_device_time
  ON device_status(device_id, last_check);

CREATE INDEX IF NOT EXISTS idx_devices_active_name
  ON devices(is_active, name);

CREATE INDEX IF NOT EXISTS idx_disc_last_seen
  ON discovered_devices(last_seen);

-- Inventario permanente de huéspedes (MACs vistas por ARP vía SSH)
CREATE TABLE IF NOT EXISTS assets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  mac_address TEXT NOT NULL UNIQUE,
  ip_address TEXT,
  hostname TEXT,
  vendor TEXT,
  first_seen TEXT,
  last_seen TEXT,
  source TEXT
);
CREATE INDEX IF NOT EXISTS idx_assets_last_seen ON assets(last_seen);
