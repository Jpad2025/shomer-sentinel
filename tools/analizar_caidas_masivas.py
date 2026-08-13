#!/usr/bin/env python3
"""analizar_caidas_masivas.py — clasifica caídas masivas como probable falso
positivo (host-side) o caída real, usando datos ya guardados en
network_monitor.db. Solo lectura, no toca nada.

Contexto (ver CLAUDE.md Sesión 70/71): a veces 8+ equipos completamente
distintos del hotel caen en el mismo batch_id sin que el guardia de
host_network_blip lo detecte (el gateway no aparece unhealthy en ese ciclo),
así que se avisan como caídas reales una por una. La firma que distingue un
falso positivo de origen host de una falla física real es la RECUPERACIÓN:
si casi todos los equipos vuelven "online" en el mismo segundo (o muy cerca),
es un síntoma del lado del host, no 8 cables/fuentes fallando a la vez.

Uso:
  python3 tools/analizar_caidas_masivas.py                  # últimos 14 días
  python3 tools/analizar_caidas_masivas.py --days 30
  python3 tools/analizar_caidas_masivas.py --min-devices 8
"""
from __future__ import annotations

import argparse
import sqlite3
from collections import Counter
from datetime import datetime

DB_PATH = "/storage/db/network_monitor.db"

# Ventanas de clasificación (ver docstring arriba)
RECUPERACION_MAX_MIN = 15   # una recuperación más allá de esto ya no cuenta como "rápida"
SINCRONIA_MAX_SEG = 60      # recuperaciones dentro de esta ventana entre sí = "al mismo tiempo"
UMBRAL_SOSPECHOSO_PCT = 0.7  # % de equipos que deben recuperarse rápido+sincronizado


def _ro_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def mass_batches(conn: sqlite3.Connection, days: int, min_devices: int):
    rows = conn.execute(
        """
        SELECT batch_id, COUNT(*) n, MIN(ts) ts
        FROM status_events
        WHERE status='offline' AND batch_id != ''
          AND ts >= datetime('now', ?)
        GROUP BY batch_id
        HAVING n >= ?
        ORDER BY ts DESC
        """,
        (f"-{days} days", min_devices),
    ).fetchall()
    return rows


def blip_suppressed(conn: sqlite3.Connection, batch_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM infra_blip_events WHERE batch_id=? LIMIT 1", (batch_id,)
    ).fetchone()
    return row is not None


def classify_batch(conn: sqlite3.Connection, batch_id: str, ts: str):
    ips = [
        r["ip"] for r in conn.execute(
            "SELECT ip FROM status_events WHERE batch_id=? AND status='offline'",
            (batch_id,),
        ).fetchall()
    ]
    total = len(ips)
    if total == 0:
        return "SIN_DATOS", {}

    placeholders = ",".join("?" for _ in ips)
    recuperaciones = conn.execute(
        f"""
        SELECT ip, MIN(ts) recovered_at FROM status_events
        WHERE ip IN ({placeholders}) AND status='online' AND ts > ?
        GROUP BY ip
        """,
        (*ips, ts),
    ).fetchall()

    rec_by_ip = {r["ip"]: r["recovered_at"] for r in recuperaciones}
    t0 = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")

    rapidas = []  # (ip, segundos_hasta_recuperar)
    for ip, rec_ts in rec_by_ip.items():
        try:
            t1 = datetime.strptime(rec_ts, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        delta_min = (t1 - t0).total_seconds() / 60.0
        if 0 <= delta_min <= RECUPERACION_MAX_MIN:
            rapidas.append((ip, (t1 - t0).total_seconds()))

    sin_recuperar = total - len(rec_by_ip)
    pct_rapidas = len(rapidas) / total if total else 0.0

    sincronia = "—"
    pct_sincronizadas = 0.0
    if len(rapidas) >= 2:
        segundos = sorted(s for _, s in rapidas)
        # cuenta cuántas caen dentro de una ventana de SINCRONIA_MAX_SEG del
        # segundo más frecuente (moda aproximada por bucket de 10s)
        buckets = Counter(int(s // 10) for s in segundos)
        bucket_top, n_top = buckets.most_common(1)[0]
        cerca = sum(
            1 for s in segundos
            if abs(s - bucket_top * 10) <= SINCRONIA_MAX_SEG
        )
        pct_sincronizadas = cerca / len(rapidas)
        sincronia = f"{pct_sincronizadas:.0%} de las recuperaciones caen en la misma ventana de {SINCRONIA_MAX_SEG}s"

    detalle = {
        "total": total,
        "recuperados_rapido": len(rapidas),
        "sin_recuperar_15min": sin_recuperar,
        "pct_rapidas": pct_rapidas,
        "sincronia": sincronia,
        "pct_sincronizadas": pct_sincronizadas,
    }

    if pct_rapidas >= UMBRAL_SOSPECHOSO_PCT and pct_sincronizadas >= UMBRAL_SOSPECHOSO_PCT:
        return "SOSPECHOSO — probable falso positivo (host-side)", detalle
    if sin_recuperar > 0 and sin_recuperar >= total * 0.3:
        return "REVISAR — varios equipos siguen sin recuperar, posible falla real", detalle
    return "MIXTO — revisar manualmente", detalle


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--min-devices", type=int, default=8)
    args = ap.parse_args()

    conn = _ro_conn()
    batches = mass_batches(conn, args.days, args.min_devices)

    if not batches:
        print(f"Sin caídas masivas (>= {args.min_devices} equipos) en los últimos {args.days} días.")
        return

    print(f"{len(batches)} caídas masivas en los últimos {args.days} días (umbral >= {args.min_devices} equipos)\n")
    for b in batches:
        batch_id, n, ts = b["batch_id"], b["n"], b["ts"]
        suprimido = blip_suppressed(conn, batch_id)
        print(f"── {ts}  batch_id={batch_id}  equipos_offline={n} ──")
        if suprimido:
            print("   ✅ SUPRIMIDO — el guardia de host_network_blip ya lo detectó y silenció.\n")
            continue
        veredicto, detalle = classify_batch(conn, batch_id, ts)
        print(f"   ⚠️  NO suprimido por el guardia — {veredicto}")
        if detalle:
            print(
                f"      recuperados en <={RECUPERACION_MAX_MIN}min: "
                f"{detalle['recuperados_rapido']}/{detalle['total']} "
                f"({detalle['pct_rapidas']:.0%}) · sin recuperar: {detalle['sin_recuperar_15min']}"
            )
            print(f"      sincronía de recuperación: {detalle['sincronia']}")
        print()


if __name__ == "__main__":
    main()
