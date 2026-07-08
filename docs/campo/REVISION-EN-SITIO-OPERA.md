# Revisión en sitio — Hotel Ópera

**Documento vivo** — USB Ingeniería / Shomer Sentinel  
**Sitio:** Hotel Ópera — Shomer `192.168.0.250` — panel `https://192.168.0.250:8443`  
**Para enviar a:** Cristian Romero, Ricardo Romero → técnico de campo  
**Contacto USB:** Juan Pablo  
**Última actualización:** **8 jul 2026** (~12:35 COT) — auditoría remota sesión 66

---

## Cómo usar este documento

1. Enviar por Telegram la sección **🔴 Urgente** cuando haya equipos offline crónicos.
2. Marcar `[x]` al completar cada ítem en sitio.
3. Anotar **fecha, técnico y resultado** al final (tabla Historial).
4. Este archivo se **complementa** después de cada auditoría Shomer — no borrar entradas viejas.

---

## Snapshot Shomer (8 jul 2026)

| Métrica | Valor |
|---------|-------|
| Infra activos | 50 online / 2 offline |
| Guardian APs | 29 online / 1 offline |
| Telegram 3 días | 138 mensajes (bajó vs semana del 2 jul) |
| Blips poller | 3 / 24 h · 56 / 7 días |

---

## 🔴 Urgente — offline (revisar ya)

| [ ] | IP | Equipo | Estado Shomer 8 jul | Qué revisar |
|-----|-----|--------|----------------------|-------------|
| [ ] | `192.168.0.148` | **AP HAB 103** | **Offline** (Guardian + Infra) | PoE, cable, LED, adoptado UniFi |
| [ ] | `192.168.0.57` | **IMP Recepción** (WF-M5899) | **Offline desde 10 jun** | Encendido, cable, IP, papel |
| [ ] | `192.168.0.243` | **Bixolon POS** | **Offline** (nuevo 8 jul) | Cable, encendido, IP |

**Resultado esperado:** equipo online en panel Shomer → Guardian o Inframonitor.

---

## 🟠 Prioridad alta — inestables / hardware

| [ ] | IP | Equipo | Estado 8 jul | Acción |
|-----|-----|--------|--------------|--------|
| [ ] | `192.168.0.58` | **IMP SCOCINA** | Online — **Pulse degradando** (71 ticks) | Cable, switch, impresora; ping OK pero latencia mala |
| [ ] | `192.168.0.168` | **SW1-P50-OFC-SISTEMAS** | Online — **GE49 ~95.534 in_errors** | Revisar cable/dispositivo en puerto GE49 |
| [ ] | `192.168.0.216` | **SW-POE-OFC-SISTEMAS** | Online — Port 7 ~2.860 errores | Revisar puerto 7 |
| [ ] | `192.168.0.250` | **Servidor Shomer** | Online — blips tipo A | Cable y **puerto del switch** donde está el mini PC |

### Flapping histórico (2 jul) — recuperados 8 jul

Ya **online**; solo confirmar en sitio si hay tiempo:

| IP | Equipo | Notas |
|-----|--------|-------|
| `192.168.0.189` | AP OFC-MANTENIMIENTO | Recuperado |
| `192.168.0.133` | SW Amalfi | Recuperado |
| `192.168.0.52` | Cámara sin identificar | Recuperado — ubicar físicamente |
| `192.168.0.136` | Terminal Ingenico | Recuperado — 3 eventos offline 24 h |

### Microcorte masivo ~13:07 (2 jul 2026) — referencia

~40 s — muchos equipos cayeron y volvieron solos. Si **no se repite**, priorizar ítems urgentes de arriba.

| [ ] | Acción en sitio |
|-----|-----------------|
| [ ] | Revisar switch administración / uplink UniFi si hay nuevo evento similar |
| [ ] | Anotar si coincide con mantenimiento eléctrico |

---

## 🟡 Servidor Shomer — blips (`host_network_blip`)

> Huéspedes **no reportaron falla de internet**. Gateway `192.168.0.1` OK entre eventos. Shomer pierde visibilidad LAN admin ~90 s — probable **cable/puerto del servidor**, no caída del hotel.

| | **Blip tipo A (Shomer)** | **Microcorte real (2 jul 13:07)** |
|---|--------------------------|-----------------------------------|
| Guardian APs | Sin oleada masiva | Muchos APs offline |
| Telegram | Suprimido (correcto) | Alertas reales |
| Acción | Cable/puerto **Shomer** | Switch admin / uplink |

### Métricas 8 jul 2026

| Medida | Valor |
|--------|-------|
| Blips confirmados (logs) | **3 / 24 h** · **56 / 7 días** |
| NIC `eno1` RX dropped | Acum. **~14,69 M** |
| Delta 24 h | Pendiente — muestreo horario activo desde sesión 66 |
| Resumen diario Telegram | ✅ 07:00 con bloque visibilidad + NIC |

### Checklist físico — servidor Shomer

| [ ] | Verificación |
|-----|--------------|
| [ ] | Cable de red del mini PC `.250` — bien conectado |
| [ ] | Puerto del switch — probar otro puerto si hay libre |
| [ ] | LEDs del puerto — sin parpadeos anómalos |
| [ ] | Anotar marca/modelo switch y **número de puerto** exacto |
| [ ] | Rack — sin calor excesivo; UPS estable en madrugada |

### Qué NO hacer

- No cambiar umbrales Shomer hasta confirmar causa física
- No desactivar supresor de blips

---

## 🟢 Recuperados — verificar que sigan OK (8 jul online)

| [ ] | IP | Equipo |
|-----|-----|--------|
| [ ] | `192.168.0.212` | SW-REST-SCALA |
| [ ] | `192.168.0.56` | POS Bixolon |
| [ ] | `192.168.0.60` | POS Bixolon |
| [ ] | `192.168.0.239` | AP REST SCALA |
| [ ] | `192.168.0.210` | AP HAB 108 |

---

## Checklist por tipo de equipo

### Switches (SNMP)

| IP | Nombre | Revisar |
|----|--------|---------|
| `192.168.0.168` | SW1-P50 | **GE49** — errores masivos |
| `192.168.0.216` | SW-POE-OFC-SISTEMAS | Port 7 errores |
| `192.168.0.146` | SW3-OFC-VENTAS | Puerto GE15 tuvo flap breve (histórico) |
| `192.168.0.1` | MikroTik | VPN `ovpn-*`: Telegram **solo conexiones** USB desde 8 jul |

### APs UniFi (Guardian)

- En rojo ahora: **HAB 103** (`.148`).
- En sitio: LED, PoE, adoptado en controlador.

### Impresoras / POS

| IP | Nombre | Estado 8 jul |
|----|--------|--------------|
| `192.168.0.57` | IMP Recepción | Offline crónico |
| `192.168.0.58` | IMP SCOCINA | Online — degradando Pulse |
| `192.168.0.243` | Bixolon | **Offline** |
| `192.168.0.56` / `.60` | Bixolon | Online |

### Cámaras / NVR

| IP | Nombre |
|----|--------|
| `192.168.0.111` | NVR Hikvision 1 |
| `192.168.0.52` | Cámara — **ubicar** físicamente |

---

## Hunter — bloqueos automáticos (informativo)

No requiere acción en sitio salvo falso positivo. Mensajes en español claro desde sesión 64.

Si bloqueo de IP **interna** (`192.168.x.x`) → avisar USB.

---

## Pendientes históricos (no urgentes)

- [ ] Failover WAN ETB automático en MikroTik
- [ ] Credenciales locales `.\sistemas` en `.41`, `.142`, `.170`
- [ ] Deep scan nocturno Tracker resto de subred
- [ ] Medición 7 días debounce OFC-COCINA
- [ ] Plantilla genérica `REVISION-EN-SITIO-TEMPLATE.md`

## Software USB — estado 8 jul 2026

| Mejora | Estado |
|--------|--------|
| Pulse Correlate (oleada + blip) | ✅ |
| Pulse EWMA (degradando) | ✅ |
| IA diagnóstico cooldown 6 h | ✅ |
| Debounce SNMP puertos | ✅ |
| Resumen blip diario 07:00 | ✅ sesión 66 |
| Delta RX dropped `eno1` | ✅ sesión 66 — esperando 2ª muestra para delta |
| VPN solo conexiones | ✅ sesión 66 |
| Sync → `.205` / GitHub | ⏳ pendiente |
| Rotar token Telegram | ⏳ pendiente |
| Topología switch padre | ⏳ opcional |

**No prioritario:** cambiar SNMP `public`.

---

## Historial de visitas

| Fecha | Técnico | Hallazgos | Ítems cerrados |
|-------|---------|-----------|----------------|
| 2 jul 2026 | USB (remoto) | Doc creado; blips 131/7d; microcorte 13:07 ≠ blip tipo A | 0 |
| 8 jul 2026 | USB (remoto) | 50/2 Infra; AP `.148` + Bixolon `.243` offline; `.58` degradando; GE49 `.168` crítico; software sesión 66 desplegado | 0 |

---

## Mensaje corto para Telegram (copiar/pegar)

```
Buenos días. Revisión Shomer Hotel Ópera — 8 jul 2026:

🔴 URGENTE
• AP HAB 103 — 192.168.0.148 (PoE/cable/AP)
• IMP Recepción — 192.168.0.57 (offline desde junio)
• Bixolon — 192.168.0.243 (caído hoy)

🟠 Si hay tiempo
• IMP SCOCINA .58 — inestable (Pulse degradando)
• Switch .168 puerto GE49 — ~95k errores SNMP
• Cable/puerto switch del servidor Shomer .250 (blips)

📄 Checklist: docs/campo/REVISION-EN-SITIO-OPERA.md

Marcar y avisar qué encontraron. Gracias.
USB / Shomer Sentinel
```

---

*Documento complementario:* `OPERA-VISIBILIDAD-CAPA2-RICARDO.md` (SNMP switches / Capa 2).
