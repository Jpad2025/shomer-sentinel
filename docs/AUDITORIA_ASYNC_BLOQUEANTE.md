# Auditoría — llamadas bloqueantes dentro de `async def` (Sesión 58, 19 jun 2026)

## Qué es esto

Guardian corre con `uvicorn --workers 1` — **un solo proceso, un solo event-loop**. Cualquier
función `async def` que llame código bloqueante de forma directa (SQLite síncrono, Redis síncrono,
`subprocess.run`, `time.sleep`) congela el servidor **completo** mientras esa llamada dura — no
solo esa petición.

Esto causó un incidente real el 19 jun 2026 en Hotel Ópera: `GET /health` (usado por
`shomer-health-check.sh` cada 30s) hacía un `CREATE TABLE IF NOT EXISTS` en cada chequeo — una
escritura innecesaria que podía chocar con otra escritura de Guardian/Hunter/Inframonitor sobre el
mismo archivo SQLite. Cuando chocaba, `/health` tardaba más de los 5s que el watchdog tolera, y el
watchdog mataba el proceso (`SIGKILL`) pensando que estaba caído. Ciclo de 7 minutos, ~14
reinicios. Ver `CLAUDE.md` §AT.1 para el detalle completo y el fix aplicado.

## Regla de oro

> Una función `async def` con SQLite/Redis síncrono o `subprocess` adentro está mal, **a menos
> que** envuelva esa llamada en `asyncio.to_thread(...)`, o se declare como `def` simple (FastAPI
> la corre en threadpool automáticamente).

## Cuándo SÍ es grave (y hay que arreglarlo)

- El endpoint lo llama un **proceso automático con un timeout corto** que castiga la demora
  (un watchdog, un poller, un health-check externo).
- El endpoint se llama con **alta frecuencia** (cada pocos segundos, todo el día).
- La llamada interna **escribe** (INSERT/UPDATE/DELETE/CREATE), no solo lee — en modo WAL los
  lectores no esperan a los escritores, pero dos escritores sí se bloquean entre sí.

## Cuándo NO es urgente

- Endpoints CRUD de uso esporádico (agregar/borrar equipo, exportar CSV, etc.) — si se traban una
  vez cada mucho tiempo, el peor caso es que el clic tarda unos segundos más. Ningún proceso
  automático lo castiga matando el servidor.
- Endpoints que solo **leen** SQLite en modo WAL — probado con carga real (lock de escritura
  sostenido 7-8s): no se ven afectados.

## Hallazgos confirmados y resueltos (Sesión 58)

| Endpoint | Problema | Fix | Archivo |
|---|---|---|---|
| `GET /health` | Hacía `CREATE TABLE IF NOT EXISTS` (escritura) en cada chequeo del watchdog — causó el crash loop real | Eliminada la escritura (tabla ya se crea al arrancar); lectura movida a `asyncio.to_thread()` con `busy_timeout=2` propio | `app/api/shomer_guardian_nodes.py::health()` |
| `GET /noc/data` | `psutil.cpu_percent(interval=0.5)` bloqueaba el event-loop 0.5s **garantizado**, en cada llamada, sin necesidad de contención — el NOC lo pide cada 30s | `interval=0.5` → `interval=None` (lectura instantánea, no bloqueante) | `app/api/shomer_noc.py::_server_resources()` |

Ambos probados con carga real: lock de escritura SQLite sostenido por 7-8 segundos en paralelo a
las peticiones. Antes del fix, `/health` se trababa; después, 0% de impacto. `/noc/data` pasó de
0.55s a 0.045s por llamada.

## Probado y descartado (falsas alarmas)

| Endpoint | Por qué se descartó |
|---|---|
| `GET /nodes` | Llama `get_db()`/`get_redis()` sin `to_thread`, pero son solo lecturas — probado con lock real de 7-8s, 0% de impacto (WAL no bloquea lectores) |
| `GET /infra/status` | Mismo patrón que `/nodes`, mismo resultado vía `/noc/data` (que comparte la misma lógica de lectura) |
| `subprocess.run()` sin `timeout=` | El barrido automático marcó 1 caso (`backups.py:439`), pero era `conn.run()` de `asyncssh` (método async real, awaited) — no `subprocess.run`. **Todos los `subprocess.run()` reales del código ya tienen `timeout=`.** |

## Inventario completo — 75 funciones `async def` con llamadas bloqueantes directas

Generado con barrido AST (`ast.walk` sobre cada `AsyncFunctionDef`, buscando `get_db()`,
`get_redis()`, `connect()`, `connect_inventory()`, `sqlite3.connect()`, `subprocess.*`, `time.sleep()`
fuera de `asyncio.to_thread()`/`run_in_executor()`). No se tocó ninguno de estos — quedan aquí como
referencia para cuando algún día alguno de ellos pase a ser de alta frecuencia o vigilado por un
proceso automático.

```
api/casador_rules.py:124       reload_suricata_rules()      subprocess.run() x4
api/shomer_audit_network.py:646  _do_scan()                  get_db() x4
api/shomer_guardian_nodes.py:340 get_nodes()                  get_redis(), get_db() x3   [probado: OK]
api/backups.py:641              _backup_windows()             subprocess.run() x3
api/shomer_guardian_discovery.py:102 delete_node()             get_db() x2, get_redis()
api/shomer_inframonitor.py:613   _poll_once()                 get_db() x2, get_redis()   [poller propio, no expuesto a watchdog]
api/shomer_inframonitor.py:1112  device_action()               get_db() x2, asyncssh.connect()
api/backups.py:419              test_backup_device()          asyncssh.connect(), subprocess.run(timeout=15)
api/backups.py:581              _backup_linux()                asyncssh.connect(), subprocess.run()
api/casador_intel.py:46         suricata_toggle()              subprocess.run() x2
api/shomer_audit_network.py:719 start_network_scan()           get_db() x2
api/shomer_config.py:351        config_scan()                  get_db() x2
api/shomer_guardian_devices.py:73 delete_router_device()       get_db(), get_redis()
api/shomer_guardian_events.py:42  get_maintenance()             get_redis(), get_db()
api/shomer_guardian_events.py:67  set_maintenance_on()          get_redis(), get_db()
api/shomer_guardian_events.py:102 set_maintenance_off()         get_redis(), get_db()
api/shomer_guardian_nodes.py:103  _poller_tick()                get_redis(), get_db()    [poller interno Guardian, cada ~10s]
api/shomer_inframonitor.py:996    get_status()                  get_redis(), get_db()    [probado vía /noc/data: OK]
api/shomer_setup.py:141           setup_apply()                 subprocess.run() x2       [wizard, una vez por instalación]
api/casador_intel.py:34           suricata_status()             subprocess.run()
api/casador_support_firewall.py:8   _mikrotik_block()           asyncssh.connect()
api/casador_support_firewall.py:48  _mikrotik_sync_block()      asyncssh.connect()
api/casador_support_firewall.py:91  _mikrotik_unblock()         asyncssh.connect()
api/casador_support_firewall.py:128 _connect_routeros()         asyncssh.connect()
api/shomer_audit.py:169          audit_logs()                   get_db()
api/shomer_audit.py:195          audit_stats()                  get_db()
api/shomer_audit.py:223          audit_export_csv()             get_db()
api/shomer_audit_network.py:466  _patch_check_single()          asyncssh.connect()
api/shomer_audit_network.py:745  get_scan_status()               get_db()
api/shomer_audit_network.py:763  get_findings()                  get_db()
api/shomer_audit_network.py:794  update_finding()                get_db()
api/shomer_audit_network.py:831  delete_finding()                get_db()
api/shomer_audit_network.py:841  get_summary()                   get_db()
api/shomer_config.py:406         config_save_nodos()             get_db()
api/shomer_drill.py:62           drill_status()                  get_db()
api/shomer_drill.py:86           drill_history()                 get_db()
api/shomer_drill.py:109          drill_history_csv()             get_db()
api/shomer_guardian_devices.py:18  list_router_devices()         get_db()
api/shomer_guardian_devices.py:30  save_router_device()          get_db()
api/shomer_guardian_devices.py:120 deactivate_device()           get_db()
api/shomer_guardian_devices.py:139 activate_device()             get_db()
api/shomer_guardian_discovery.py:21  get_discovered()             get_db()
api/shomer_guardian_discovery.py:57  promote_device()             get_db()
api/shomer_guardian_discovery.py:144 delete_discovered()          get_db()
api/shomer_guardian_events.py:20   get_events()                  get_redis()
api/shomer_guardian_events.py:143  get_node_maintenance()        get_redis()
api/shomer_guardian_events.py:162  set_node_maintenance_on()     get_redis()
api/shomer_guardian_events.py:200  set_node_maintenance_off()    get_redis()
api/shomer_guardian_nodes.py:438   heartbeat()                   get_redis()             [recibido de APs reales — alta frecuencia, solo Redis]
api/shomer_guardian_nodes.py:546   reset_failures()               get_redis()
api/shomer_guardian_nodes.py:561   reboot_node()                  get_redis()
api/shomer_guardian_nodes.py:608   get_logs()                     get_db()
api/shomer_guardian_server_health.py:269  _server_health_tick()   get_redis()
api/shomer_guardian_server_health.py:367  _heartbeat_report_tick() get_redis()
api/shomer_guardian_server_health.py:419  get_server_metrics()    get_db()
api/shomer_guardian_server_health.py:486  get_wan_status()        get_redis()
api/shomer_incidents.py:151       list_incidents()               get_db()
api/shomer_incidents.py:173       incident_stats()                get_db()
api/shomer_incidents.py:212       get_incident()                  get_db()
api/shomer_incidents.py:224       ack_incident()                  get_db()
api/shomer_incidents.py:244       close_incident()                get_db()
api/shomer_incidents.py:264       export_incidents_csv()          get_db()
api/shomer_inframonitor.py:458    _send_infra_alert()             get_redis()
api/shomer_inframonitor.py:923    list_devices()                  get_db()
api/shomer_inframonitor.py:954    add_device()                    get_db()
api/shomer_inframonitor.py:985    remove_device()                 get_db()
api/shomer_inframonitor.py:1077   get_snmp_data()                 get_db()
api/shomer_setup.py:350           setup_scan_ips()                subprocess.run()        [wizard]
api/shomer_setup.py:480           setup_test_wifi()               subprocess.run()        [wizard]
api/shomer_status_events.py:835   api_confirm_outage()            get_db()
api/shomer_status_events.py:870   api_status_events()             get_db()
api/shomer_system_status.py:350   system_logs()                   subprocess.run(timeout=...)  [usado por /system-status, auto-refresh 30s]
api/shomer_topology.py:249        api_topology_links()            get_db()
backend/routes/discovery.py:75    scan_now()                      subprocess.run()        [nmap, manual]
```

## Próxima vez que se revise esto

Si alguno de los de la lista pasa a ser sondeado por un proceso automático (un nuevo watchdog,
un poller, una integración Wazuh con timeout corto, el bot llamándolo cada pocos segundos),
**ese es el momento de aplicarle el mismo fix** que a `/health` — no antes. No se recomienda
refactorizar los 75 de una sola vez sin que haya una necesidad concreta detrás.
