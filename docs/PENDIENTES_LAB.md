# Pendientes lab (recordatorio operativo)

Actualizado: **28 jul 2026** · Dueño: Juan Pablo (único operador)

## Tokens Telegram lab (SIN conflicto ahora)

| Host | Bot | Token |
|------|-----|-------|
| Ópera | ON | producción (exclusivo) |
| .245 (`shomer245`) | ON | token lab actual |
| .205 | OFF / disabled | ⏳ crear token BotFather propio |
| .243 | OFF / disabled | ⏳ crear token BotFather propio |

**Regla:** un token = un poller. No compartir. No usar el de Ópera en labs.

**Cuando lo hagas (más tarde):**
1. BotFather → nuevo bot por host
2. Poner `TELEGRAM_BOT_TOKEN` (+ chat) en `/storage/shomer-agent/.env` de ese host
3. `sudo systemctl enable --now shomer-agent.service`
4. Verificar: `docker exec shomer-agent date` (Bogotá) y 0 Conflicts en logs

## Memoria `/guardar` → decisiones (siguiente nivel)

Ya existe `knowledge_decision()` (consejo en alertas/IA, no piloto auto).

Mejoras posibles (priorizar cuando digas adelante):
1. Botón rápido "Falso positivo Hunter" / "Fue cable/PoE" (tags limpios sin depender del texto libre)
2. Resumen diario: bloque "lo que aprendimos esta semana" desde knowledge.db
3. Regla suave: si 3+ reinicios resolvieron el mismo AP → sugerir `no_reboot` o mantenimiento (solo sugerencia)
4. Chat IA: tool explícita `consultar_memoria(ip)` siempre inyectada al diagnosticar
5. Export `/bitacora` + knowledge a CSV mensual para el hotel

## Sync código

- Maestro: Ópera
- Agente: git `shomer-agent` (push desde Ópera OK)
- Core `/opt/network_monitor`: sync rsync **sin** `--delete`, **sin** SITE.md / .env / *.db
- Nunca `git add -A` a ciegas en labs (puede meter BDs locales)
- **28 jul:** sync NOC (`noc.html`, `shomer_noc.py`, `alerts.py`) + bloque IA + tipografía soporte USB + docs Ópera → `.205` / `.245` / `.243` + push GitHub (`shomer-sentinel` / `shomer-agent`)

## NOC (pantalla)

- `/noc` = TV / operaciones (misma plantilla en labs; token local por sitio)
- No inventar alertas Telegram nuevas desde el NOC (Guardian/Infra/Hunter ya alertan)
- No reintroducir vista “semáforo rojo” / `/noc/tecnico` sin pedido explícito

## Limpieza git (seguridad)

Commit `16be896` metió BDs/backups por error; `de79dcd` los quitó del árbol actual.
⏳ Pendiente (requiere tu OK + force-push): `git filter-repo` para borrarlos del historial remoto.

## Push seguro (git)

- **Nunca** `git add -A` en labs: puede meter `*.db` / backups locales.
- Antes de push: `git status` — solo código/docs; 0 archivos `.db` / `.tar.gz`.
- `SITE.md` y `.env` no van a git.
- HEAD actual sin BDs trackeados. Historial antiguo (`16be896`) aún tiene blobs hasta filter-repo (requiere OK + force-push; no urgente para operar).

## Pruebas pendientes (dejar correr; recordar)

Cuando pruebes a mano (Ópera / Telegram):

1. **Tags memoria:** tras reboot o alerta → botones Reinicio resolvió / Cable/PoE / Falso positivo
2. **Chat IA:** preguntar por una IP y verificar que use `consultar_memoria` (antecedente/consejo)
3. **Horarios Bogotá:** mañana ~08:00 — resumen diario + informe puertos (mismo briefing)
4. **Noche sin spam:** mant. logs / preventivo / backup semanal — Telegram solo si fallan
5. **Tokens lab (más tarde):** BotFather propio para .205 y .243; hasta entonces bot OFF

No es urgente. Sistema en marcha.
