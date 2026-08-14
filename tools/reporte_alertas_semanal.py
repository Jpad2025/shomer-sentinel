#!/usr/bin/env python3
"""reporte_alertas_semanal.py — cuántos mensajes se mandaron a Telegram y
cuántos se suprimieron, por mecanismo. Solo lectura, no toca nada.

Contexto (ver CLAUDE.md "Mapa de decisión de alertas", Sesión 72): hay 5-6
mecanismos independientes que deciden si un evento se avisa o se calla. No
había forma de medir con datos si de verdad bajaba el ruido cada vez que se
tocaba uno — este reporte junta lo que cada mecanismo ya guarda en su propia
tabla/BD y lo resume en un solo lugar.

Uso:
  python3 tools/reporte_alertas_semanal.py                 # últimos 7 días
  python3 tools/reporte_alertas_semanal.py --days 30
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from collections import Counter

sys.path.insert(0, "/opt/network_monitor")
from app.api.shomer_network_blip import gateway_unhealthy  # noqa: E402

MEMORIA_DB = "/storage/shomer-agent/data/memoria.db"
KNOWLEDGE_DB = "/storage/shomer-agent/data/knowledge.db"
NETWORK_DB = "/storage/db/network_monitor.db"


def _ro(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def seccion_mensajes_enviados(days: int) -> None:
    print(f"── Mensajes Telegram enviados (memoria_alertas, últimos {days}d) ──")
    try:
        conn = _ro(MEMORIA_DB)
    except Exception as e:
        print(f"   (no se pudo leer {MEMORIA_DB}: {e})\n")
        return
    total = conn.execute(
        "SELECT COUNT(*) n FROM memoria_alertas WHERE ts >= datetime('now', ?)",
        (f"-{days} days",),
    ).fetchone()["n"]
    print(f"   Total: {total}")
    rows = conn.execute(
        """
        SELECT monitor, COUNT(*) n FROM memoria_alertas
        WHERE ts >= datetime('now', ?)
        GROUP BY monitor ORDER BY n DESC LIMIT 10
        """,
        (f"-{days} days",),
    ).fetchall()
    for r in rows:
        print(f"     {r['monitor'] or '(sin monitor)':<22} {r['n']}")
    conn.close()
    print()


def seccion_blips(days: int) -> None:
    print(f"── Caídas suprimidas por host_network_blip (últimos {days}d) ──")
    try:
        conn = _ro(NETWORK_DB)
    except Exception as e:
        print(f"   (no se pudo leer {NETWORK_DB}: {e})\n")
        return
    rows = conn.execute(
        """
        SELECT gateway_status, gateway_loss, gateway_rtt_ms, offline_count,
               total_devices, batch_id, ts
        FROM infra_blip_events
        WHERE ts >= datetime('now', ?)
        ORDER BY ts DESC
        """,
        (f"-{days} days",),
    ).fetchall()
    conn.close()

    # Mismo criterio que usa el código real (gateway_unhealthy) para no
    # duplicar la lógica de umbrales y desincronizarse de ella: gateway
    # offline, o degraded con pérdida/RTT por encima del umbral, = blip
    # clásico por gateway. Lo que NO cumple eso = blip masivo puro (Sesión 72).
    por_gateway = sum(
        1 for r in rows
        if gateway_unhealthy(r["gateway_status"], r["gateway_loss"], r["gateway_rtt_ms"])
    )
    por_masivo = len(rows) - por_gateway
    print(f"   Total suprimidos: {len(rows)}  (por gateway caído: {por_gateway} · por caída masiva sin gateway: {por_masivo})")
    if rows:
        equipos_evitados = sum(r["offline_count"] for r in rows)
        print(f"   Equipos que NO mandaron alerta individual gracias a esto: ~{equipos_evitados}")
    print()


def seccion_escalamiento(days: int) -> None:
    print(f"── Incidentes crónicos (incident_escalation, últimos {days}d) ──")
    try:
        conn = _ro(KNOWLEDGE_DB)
    except Exception as e:
        print(f"   (no se pudo leer {KNOWLEDGE_DB}: {e})\n")
        return
    cutoff = time.time() - days * 86400
    rows = conn.execute(
        "SELECT state, event_count, reopened_count, escalated_count FROM escalation_incidents "
        "WHERE opened_at >= ?",
        (cutoff,),
    ).fetchall()
    conn.close()

    if not rows:
        print("   Sin incidentes nuevos en el período.\n")
        return

    estados = Counter(r["state"] for r in rows)
    eventos_agrupados = sum(max(0, r["event_count"] - 1) for r in rows)
    escalados = sum(1 for r in rows if r["escalated_count"] > 0)
    print(f"   Incidentes abiertos: {len(rows)}")
    for st, n in estados.most_common():
        print(f"     estado={st:<14} {n}")
    print(f"   Mensajes de repetición evitados (agrupados en digest en vez de uno c/u): ~{eventos_agrupados}")
    print(f"   Escalados al coordinador: {escalados}")
    print()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, default=7)
    args = ap.parse_args()

    print(f"Reporte de alertas — últimos {args.days} días\n")
    seccion_mensajes_enviados(args.days)
    seccion_blips(args.days)
    seccion_escalamiento(args.days)
    print("Nota: no incluye supresión de 'recuperado' repetido (is_flapping, Sesión 71)")
    print("ni compactación de flappers crónicos (Sesión 69) -- esos no quedan en tabla,")
    print("solo se ven contando mensajes por texto en memoria_alertas si hace falta.")


if __name__ == "__main__":
    main()
