# Hunter — MikroTik RouterOS nativo (bloqueo por address-list)

Shomer Hunter puede bloquear IPs en un **MikroTik con RouterOS nativo** (sin flashear a OpenWrt). El panel usa `hunter.firewall_type=routeros` y se conecta por SSH igual que a OpenWrt.

## Cómo funciona (dos piezas)

| Pieza | Quién la crea | Qué hace |
|-------|---------------|----------|
| **Address-list** `shomer-blocked` | Shomer (automático) | Guarda las IPs que Hunter debe bloquear |
| **Regla filter DROP** en `chain=forward` | **Técnico — una sola vez** | Descarta tráfico cuyo origen esté en `shomer-blocked` |

Shomer **solo escribe en la lista**. Si falta la regla DROP, el panel puede mostrar la IP como bloqueada (`firewall_blocked=1`) pero **el tráfico sigue pasando** por el router.

### Caso real — Hotel Ópera (jun 2026)

- IP `190.60.195.10` estaba en `shomer-blocked` desde el 7/jun.
- **No existía** regla `drop` en `forward` para esa lista.
- Suricata seguía generando alertas (IDS en espejo) aunque la BD decía “bloqueada”.
- Tras agregar la regla DROP al inicio de `forward`, el bloqueo pasó a ser efectivo.

## Configuración en el panel Hunter

1. **Tipo de firewall:** MikroTik RouterOS  
2. **IP / usuario / contraseña SSH** del router (típico: IP LAN del gateway, ej. `192.168.0.1`)  
3. Guardar → usar **Verificar regla DROP**  
4. Si falta la regla:
   - **Producción / sitios conservadores:** aplicar **manualmente** el comando de abajo en Winbox o terminal.
   - **Laboratorio:** opcional **Aplicar regla DROP** desde el panel si `hunter.routeros_auto_drop_enabled=true` en configuración (por defecto está desactivado).

## Comando manual (Winbox / terminal)

Ejecutar **una vez** en el MikroTik (o equivalente desde el panel):

```
/ip firewall filter add chain=forward action=drop src-address-list=shomer-blocked place-before=0 comment="Shomer-Hunter"
```

- `place-before=0` coloca la regla al **inicio** de `forward`, antes de reglas hotspot u otras que podrían aceptar el tráfico.
- La misma regla sirve para **todas** las IPs que Hunter bloquee (manual, autobloqueo o Wazuh).

### Verificar

```
/ip firewall filter print where chain=forward and action=drop and src-address-list=shomer-blocked
/ip firewall address-list print where list=shomer-blocked
```

Debe existir **al menos una** regla DROP y las IPs bloqueadas deben aparecer en la lista.

## Flujo cuando Hunter bloquea una IP

```
Suricata / Wazuh / panel / bot
        → POST /remedies/block
        → SSH al MikroTik
        → /ip firewall address-list add address=<IP> list=shomer-blocked
        → La regla DROP existente empieza a descartar ese origen en forward
```

Desbloqueo: quita la IP de la lista (`remove [find …]`). La regla DROP permanece.

## Sincronizar tras cambios

- **Sincronizar Firewall** en el panel re-aplica todas las IPs activas de la BD a la address-list (útil si alguien borró entradas en el router).
- No crea la regla DROP — eso es independiente.

## OpenWrt vs RouterOS

| | OpenWrt / Linux | MikroTik RouterOS |
|---|-----------------|---------------------|
| Mecanismo | `iptables -I FORWARD -s IP -j DROP` por IP | Una regla DROP + lista `shomer-blocked` |
| Paso manual | Ninguno (si SSH funciona) | **Regla DROP obligatoria** |
| `hunter.firewall_type` | `openwrt` (default) | `routeros` |

## API (panel / integraciones)

| Método | Ruta | Uso |
|--------|------|-----|
| GET | `/remedies/firewall/routeros/verify` | Cuenta reglas DROP y entradas en lista |
| POST | `/remedies/firewall/routeros/ensure-drop-rule` | Crea regla DROP si falta |

Requieren sesión autenticada y `hunter.firewall_type=routeros`.

## Checklist campo — sitio con MikroTik RouterOS

- [ ] `hunter.firewall_type` = `routeros`  
- [ ] Credenciales SSH probadas desde el Shomer (`ssh admin@<IP>`)  
- [ ] Regla DROP verificada (panel o comando manual)  
- [ ] Prueba con IP de laboratorio `198.51.100.1` — **nunca** IP operativa del cliente  
- [ ] `hunter.subnets` incluye todas las VLANs internas (lista de exclusión)  
- [ ] SPAN / espejo configurado si aplica detección Suricata  

## Bot Telegram — qué avisa y qué no

| Situación | ¿Bot avisa? |
|-----------|-------------|
| IP **nueva** bloqueada (últimos 10 min) | ✅ `watch_hunter` — una vez |
| IP ya bloqueada hace días (ej. `.10`) | ❌ Ya no repite resumen cada 6 h (fix jun 2026) |
| Riesgos altos marcados **terminado** en panel | ❌ `watch_network_audit` solo si **sube** el conteo crítico/alto |
| Alertas en panel Hunter (Suricata/espejo) | Normal — IDS sigue viendo tráfico espejado; no es spam del bot |

## Referencia código

- `app/api/casador_support_firewall.py` — `_routeros_block`, `_routeros_verify_setup`, `_routeros_ensure_drop_rule`
- `app/templates/hunter.html` — sección Firewall con verificación en UI
- `/storage/shomer-agent/core/monitor.py` — `watch_hunter`, `watch_active_threats`, `watch_network_audit`
