# Shomer Sentinel 2.0 — Guía maestra del sistema

**Producto:** appliance de visibilidad, inventario, resiliencia (Guardian) e IDS (Hunter) en la LAN del cliente.  
**Vigencia del documento:** 2026-06-10 (Sesión 51 — monitor integrado en ficha, timeout WMI 90 s, parches Hunter; manifiesto detallado en `CLAUDE.md` §AK).  
**Audiencia:** ingeniería, soporte L2/L3, recuperación ante pérdida del equipo o del sitio.

---

## 1. Qué resuelve Shomer

- **Visión unificada** de la red: panel web, sin IPs ni topología fija en código (ver directiva en `CLAUDE.md` §0).
- **Core (puerto 8000):** panel, autenticación, **Guardian** (GL.iNet y nodos, failsafe, Telegram), **Hunter** (Suricata, integración con firewall OpenWrt del perímetro, bloqueo bajo reglas y política).
- **Tools (puerto 8001):** **Tracker** (inventario, escaneo, export, snapshots) y **Protector** (Restic, equipos, B2). El navegador habla con **8000**; el front proxifica `/tracker/*`, `/snapshot/*`, `/backups/*` a 8001.
- **Persistencia** en `/storage/db/`; logs en `/var/log/shomer/`; backups de producto bajo criterio Restic y panel Protector.

---

## 2. Equipo de referencia (campo y laboratorio)

| Elemento | Detalle típico |
|----------|------------------|
| Plataforma | Mini PC (p. ej. Intel N100, 16 GB RAM, NVMe) |
| SO | Ubuntu 22.04 LTS |
| `enp2s0` | Gestión: panel, SSH, Guardian hacia la LAN; acceso del técnico |
| `enp4s0` | Captura: tráfico espejado hacia **Suricata** (Hunter). Requiere `rp_filter=0` (ver guía de instalación) |
| Código | `/opt/network_monitor/` |
| Python | `/opt/network_monitor/venv/bin/python` (unidades `systemd` suelen invocar este venv) |

Nombres de interfaz en otro chasis: variables de entorno `SHOMER_MANAGEMENT_INTERFACE` / `SHOMER_MIRROR_INTERFACE` y fábrica en `tools/factory_reset_network.sh`.

---

## 3. Procesos, puertos y unidades *systemd*

| Servicio | Puerto | Módulo Uvicorn | Función |
|----------|--------|----------------|---------|
| `shomer-guardian.service` | **8000** | `app.api.main:app` | Core: UI, API, Guardian, Hunter |
| `shomer-tools.service` | **8001** (`127.0.0.1`) | `app.api.main_tools:app` | Tracker + Protector |
| `shomer-health-watchdog.timer` | — | — | Comprueba 8000/8001; reinicia si hace falta |
| `redis-server` (sistema) | 6379 | — | Colas/estado Guardian; obligatorio para failsafe y nodos |
| `suricata` | — | — | IDS; captura en `enp4s0` (según `suricata.yaml`) |

**No** usar un segundo servicio en 8001: el producto unifica Tools en `shomer-tools`. Unidades legacy (p. ej. `network-monitor`, `shomer-monitor`) deben seguir *neutralizadas* (no `.service` activo con ese nombre en producción).

**Entrada HTTPS habitual:** nginx en **8443** → proxy a **8000** (CORS y cabeceras en la app, no en nginx para orígenes).

**Variables críticas:** `/etc/shomer/shomer-runtime.env` (p. ej. `JWT_SECRET`, `SHOMER_CORS_ORIGINS`) — permisos restrictivos, referenciados por *drop-ins* de `shomer-guardian` y `shomer-tools`.

---

## 4. Mapa de código (alto nivel)

Ruta base: `app/`.

| Área | Ficheros / directorios | Rol |
|------|------------------------|-----|
| Entrada 8000 | `app/api/main.py` | *Lifespan*: poller Guardian + salud de servidor; monta `shomer_*` y routers de seguridad |
| Entrada 8001 | `app/api/main_tools.py` | Auth compartida, `inventory`, export, snapshot, `backups` |
| UI / config | `app/api/shomer.py`, `shomer_config.py`, `shomer_setup.py` | Panel, `/config/*`, asistente `/setup` |
| Guardian | `shomer_guardian_*.py`, `shomer_proxies.py` | Nodos, eventos, descubrimiento, proxies a 8001 |
| Salud / WAN | `shomer_guardian_server_health.py`, `shomer_guardian_health_checks.py` | Métricas, quorum WAN, integración con failsafe |
| Hunter / Casador | `casador*.py` bajo `app/api/` | Reglas, Suricata, bloqueo, `system_state` |
| Tracker | `app/api/inventory*.py`, `app/scripts/tracker/`, `app/scripts/scanner.py` | Inventario, escaneo profundo, OUI, WMI/SSH/SNMP, LLDP |
| Protector | `app/api/backups.py`, `app/backend/protector.py` | Restic, equipos, B2 |
| Datos | `app/backend/db.py` | Rutas: `STORAGE_DB`, BDs, `LOG_DIR`, credenciales |

*Tests de humo:* `tests/test_smoke_api.py` (Core + Tools + rutas clave). *Suite Tracker:* `tests/test_inventory_*.py`.

---

## 5. Datos, rutas y resiliencia

- **Canónico:** `STORAGE_DB` → `/storage/db/` con al menos:
  - `network_monitor.db` — Guardian, `system_state`, métricas, *infra_nodes*, *failsafe_state*, etc.
  - `inventory.db` — *assets*, *network_credentials*, *inventory_snapshots* (Tracker).
- **No** depender de `/opt/network_monitor/database/` en entregas nuevas; documentación de réplica: `docs/RUTAS_Y_REPLICACION.md`.
- **Logs:** `/var/log/shomer/api.log` (8000), `tools_api.log` (8001), `tracker.log`, `protector.log`, etc.
- **Restic / Protector:** repositorio y contraseña vía entorno o BD; no versionar secretos.
- **Redis:** claves `status:*`, `failures:*`, mantenimiento `shomer_maintenance`, contadores de *degraded* / reboot — documentados en `CLAUDE.md` §10.

---

## 6. Módulos funcionales (resumen)

### 6.1 Guardian

- Polling de nodos (p. ej. GL.iNet) con ping, SSH, pruebas WAN/DNS/HTTP desde el AP.
- Estados: *online*, *offline*, *no-internet*, *degraded*; umbrales y Telegram desde `/config/system` (BD + `system_state`).
- Reboot automático bajo reglas y **cooldown**; kill-switch con Redis `shomer_maintenance=1`.
- Código: `shomer_guardian_nodes.py` (*poller*), `shomer_guardian_health_checks.py`.

### 6.2 Tracker

- *Quick scan* / *deep scan* vía `scanner.py`; fingerprint WMI (DCOM + PowerShell/SMB para software), SSH (incl. macOS), SNMP, banner web, LLDP pasivo.
- **Timeout WMI:** 90 s por PC Windows (`TIMEOUT_CRITICAL_SEC` + `EXTRACTOR_SSH_WMI_TIMEOUT`) — necesario para software + monitores + USB en un solo paso.
- **Ficha del equipo (panel):** monitor integrado (portátil/All-in-One), monitores externos (0–3), docks/USB detectados, impresoras locales, usuario logueado al escanear. Campos en `inventory.db` — ver `CLAUDE.md` §G y §AK.3.
- **Redes grandes:** deep scan por VLAN de noche; no un solo escaneo de 500+ equipos en horario pico (`CLAUDE.md` §AK.6).
- Excel/PDF/etiquetas y **snapshots** con protocolo de backup/restore en `CLAUDE.md` §13.8.1.
- **Verdad** del inventario: tabla en `inventory.db` — exportar Excel como evidencia, no sustituto de procedimiento de snapshot.

### 6.3 Hunter

- Suricata sobre `enp4s0`; reglas en ficheros bajo `/etc/suricata/` (laboratorio: p. ej. SID `9009001` para ICMP de prueba — desactivar en producción, ver `CLAUDE.md` §AJ.4).
- **Riesgos de Red:** nmap `-sV` + auditoría de parches Windows (Windows Update vía WMI, Sesión 51) sobre activos del Tracker.
- Alertas hacia Wazuh / panel; bloqueo vía SSH al firewall usando **iptables** (OpenWrt Linux). Integración Wazuh: script `tools/cazador/wazuh_shomer_block.py` → `POST /remedies/block` + `X-Shomer-Integration-Key`.
- Multi-subred: routing L3 y políticas en el cliente; Guardian no exige tercera NIC *por diseño* (ver `CLAUDE.md` §C).
- **Verificado en lab (10/05/2026):** cadena Wazuh→API→OpenWrt `.206`→Telegram funciona end-to-end. Bugs críticos corregidos (ver `CLAUDE.md` §E.1).
- **Sesión 24 (10/05/2026):** columna `firewall_blocked` en BD (distingue "bloqueado en red" vs "solo registrado"), timeout SSH configurable (`hunter.firewall_timeout`), historial desbloqueados con export CSV en panel.
- **Pendientes campo (P1–P4):** espejo SPAN en sitio nuevo, Wazuh manager cliente, SID hotel, auto_block por sitio — sesiones de campo aparte.

### 6.4 Protector

- Backups con Restic; equipos Windows/Linux desde panel; B2 opcional. Logs `protector.log`.
- **B2 restore desde panel (Sesión 26):** `GET /backups/b2/snapshots` lista snapshots en nube con columna Equipo. `POST /backups/b2/restore/{id}` descarga al Shomer en `/srv/shomer_restore/{id}/`. `GET /backups/restore/{id}/download` sirve ZIP al navegador del técnico — sin CLI, sin Linux.
- **Directorio restore:** `/srv/shomer_restore/` — propietario `usb_admin:usb_admin`, permisos 755. Debe existir antes del primer restore.
- **Toggle schedule por equipo:** tabla snapshots locales muestra botón ⏸ Pausar auto / ▶ Activar auto por fila. Útil cuando un equipo está apagado y se quiere evitar errores del scheduler.
- **Pendiente verificar campo:** flujo completo restore B2 → ZIP → descarga navegador (tamaños típicos documentos 10–400 MB; > 2 GB no recomendado por browser).

---

## 7. Red y endurecimiento

- **Deploy a producción:** solo con **autorización explícita de Juan Pablo**; solo **código** (`app/`), nunca BD ni config de sitio. Regla completa: `docs/REGLAS_DEPLOY.md` · `CLAUDE.md` §B.3.
- **8000/8001** no expuestos a Internet; acceso operador vía **8443** o LAN. UFW: ajustar subred del cliente (no dejar reglas de lab fijas). Ver `CLAUDE.md` §7.
- **bnonce** compartido entre 8000 y 8001: derivado de `JWT_SECRET` en `auth_api.py` (tokens válidos en ambos procesos).
- *Rate limits* y CORS: `cors_util.py` + `SHOMER_CORS_ORIGINS`.

---

## 8. Recuperación “desde cero” (pérdida de equipo o sitio)

Orden lógico; adaptar a backup disponible (Restic, copia de `/storage/db/`, imágen del SO).

1. **Hardware** y **Ubuntu 22.04** con particiones alineadas al manifiesto ( `/var` logs, `/storage` datos, `/opt` código ).
2. Clonar o desplegar **`/opt/network_monitor/`** (misma versión/rama que producción) y `venv` (`pip install -r` según procedimiento interno).
3. Restaurar **`/storage/db/`** desde backup coherente (mismo *schema*). Verificar permisos y propietario del servicio.
4. Configurar **`/etc/shomer/shomer-runtime.env`** (`JWT_SECRET`, etc.).
5. Instalar y habilitar unidades: **`shomer-guardian`**, **`shomer-tools`**, **watchdog**, **redis**, **suricata**, **nginx** según imagen.
6. Aplicar **netplan** (IPs cliente), **`sysctl` rp_filter** en `enp4s0`, y reglas de firewall perimetral (MikroTik) como en `Instalacion_Shomer_Produccion_Tecnico.md`.
7. Probar: `systemctl is-active` sobre servicios, `ss -tlnp` en 8000/8001, `curl` a panel, *smoke* `pytest`, escaneo mínimo en Tracker, alerta de prueba en Hunter si el espejo está operativo.
8. **Documentar** fuera del panel (ticket): versión, fecha, y comprobación §13.8.1 si aplica *snapshot*.

---

## 9. Verificación rápida (comandos)

```bash
sudo systemctl is-active shomer-guardian.service shomer-tools.service redis-server suricata
sudo ss -tlnp | egrep ':(8000|8001)\b'
sudo tail -n 5 /var/log/shomer/api.log /var/log/shomer/tools_api.log
```

Reinicio limpio 8000/8001 (evitar *restart* ciego con huérfanos en puerto): parar servicio, `kill` puerto si aplica, `start` — secuencia en `CLAUDE.md` §8.

---

## 10. Documentos hermanos

| Documento | Uso |
|-----------|-----|
| `docs/EQUIPOS.md` | **Registro por appliance:** NICs, Suricata, lab vs producción, qué sincronizar con `deploy.sh`. |
| `SITE.md` (en cada servidor) | Config **solo de ese cliente/sitio** — subnets, SPAN, firewall. No copiar entre hoteles. |
| `tools/suricata_lab_setup.sh` | Post-instalación Suricata en lab (ruleset ET, `SHOMER_LAB_NO_SPAN`, NIC espejo). |
| `CLAUDE.md` | Manifiesto de desarrollo: detalle de bugs cerrados, §13.8, sesiones, listas largas. |
| `app/static/docs/Instalacion_Shomer_Produccion_Tecnico.md` | **Instalación en campo** desde cero (técnico). |
| `app/static/docs/Instalacion_Remota_Tailscale.md` | **Instalación remota vía Tailscale** — acceso SSH desde Utah, flujo completo Bogotá y futuros clientes. |
| `app/static/docs/Tracker_inventario_snapshot_y_excel.md` | Explicación BD vs Excel y snapshots. |
| `app/static/docs/Tracker_cuenta_servicio_inventario.md` | Cuenta de servicio / WMI / SSH en equipos del cliente. |
| `app/static/docs/Hunter_pruebas_campo_checklist.md` | Checklist una página: espejo, Suricata, alerta de lab, Wazuh. |
| `app/static/docs/Anexo_MikroTik_TFTP_OpenWrt.md` | Anexo **detallado** (p. ej. TFTP, OpenWrt en MikroTik). La guía prioritaria es `Instalacion_*`. |
| `docs/MODULOS_INSTALADOS_ARCHIVOS_Y_URLS.md` | Referencia de URLs y módulos. |

---

## 11. Cumplimiento y pruebas

- *Smoke* automatizado: `tests/test_smoke_api.py` — se espera 100% verde antes de cierre de entrega.
- *Campo* (Colombia y otros): validar espejo → Suricata, reglas, Telegram, subredes reales, credenciales WMI/SSH, y snapshot según acuerdo con el cliente. Los ítems abiertos de laboratorio (p. ej. tráfico real por SPAN) constan en `CLAUDE.md` §4.1 y §5.

---

*USB Ingeniería SAS — documento de producto. Mantener en sync con imágenes de sistema y con `Instalacion_Shomer_Produccion_Tecnico.md` al cambiar el procedimiento de instalación.*

