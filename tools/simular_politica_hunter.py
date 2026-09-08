#!/usr/bin/env python3
"""Simulacro de la política de Hunter contra el tráfico REAL ya registrado.

Responde, con evidencia y sin tocar el firewall: si activo el bloqueo ahora,
¿qué cortaría exactamente? Lee las alertas de Suricata (eve.json + rotados) y
aplica la MISMA lógica que usa el autobloqueo en producción —
_firma_es_ruido(), min_severity, only_external y la lista de excepciones— sin
ejecutar ninguna acción.

Nació del incidente del 8 sep 2026 en Ópera: Hunter bloqueó los DNS de Google
y dejó al hotel sin internet, y el proveedor tuvo que apagar la regla de
firewall y el puerto del espejo. Antes de volver a activar el bloqueo hay que
poder demostrar qué se va a cortar.

Uso:
    python3 tools/simular_politica_hunter.py             # últimas 24h
    python3 tools/simular_politica_hunter.py --horas 72
    python3 tools/simular_politica_hunter.py --todo
"""
from __future__ import annotations

import argparse
import glob
import gzip
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/opt/network_monitor")

from app.api.casador_blocking import (  # noqa: E402
    _auto_block_policy,
    _firma_es_ruido,
    _ip_in_exceptions,
)
from app.api.casador_support import _is_external_ip  # noqa: E402

LOG_DIR = "/var/log/suricata"

# Servicios que jamás deberían quedar cortados en un hotel. No son la defensa
# (esa es la política): son el detector de que la política se rompió.
IPS_CRITICAS = {
    "8.8.8.8": "DNS Google", "8.8.4.4": "DNS Google",
    "1.1.1.1": "DNS Cloudflare", "1.0.0.1": "DNS Cloudflare",
    "208.67.222.222": "DNS OpenDNS", "9.9.9.9": "DNS Quad9",
}
REDES_CRITICAS = (
    ("142.250.", "Google"), ("142.251.", "Google"), ("172.217.", "Google"),
    ("216.58.", "Google"), ("13.107.", "Microsoft"), ("20.190.", "Microsoft"),
    ("17.", "Apple"), ("185.125.190.", "Canonical/Ubuntu"),
    ("23.2.", "Akamai"), ("23.218.", "Akamai"), ("2.21.", "Akamai"),
    ("151.101.", "Fastly"), ("104.16.", "Cloudflare"),
)


def servicio_critico(ip: str) -> str:
    if ip in IPS_CRITICAS:
        return IPS_CRITICAS[ip]
    for prefijo, nombre in REDES_CRITICAS:
        if ip.startswith(prefijo):
            return nombre
    return ""


def abrir(path: str):
    if path.endswith(".gz"):
        return gzip.open(path, "rt", errors="replace")
    return open(path, "r", errors="replace")


def leer_alertas(desde: datetime | None):
    """Todas las alertas de eve.json y sus rotados, más viejo primero."""
    archivos = sorted(
        glob.glob(os.path.join(LOG_DIR, "eve.json*")),
        key=lambda p: os.path.getmtime(p),
    )
    for path in archivos:
        try:
            with abrir(path) as fh:
                for linea in fh:
                    if '"event_type":"alert"' not in linea:
                        continue
                    try:
                        ev = json.loads(linea)
                    except Exception:
                        continue
                    if ev.get("event_type") != "alert":
                        continue
                    if desde:
                        ts = (ev.get("timestamp") or "")[:19]
                        try:
                            if datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S").replace(
                                tzinfo=timezone.utc
                            ) < desde:
                                continue
                        except Exception:
                            pass
                    yield ev
        except OSError:
            continue


def decidir(ip: str, firma: str, sev: int, pol: dict) -> tuple[str, str]:
    """Misma cadena de decisión que el autobloqueo real."""
    if not pol["enabled"]:
        return "NO", "autobloqueo deshabilitado"
    ruido = _firma_es_ruido(firma)
    if ruido:
        return "NO", f"regla informativa/protocolo ({ruido})"
    if sev > int(pol["min_severity"]):
        return "NO", f"severidad {sev} > umbral {pol['min_severity']}"
    if pol["only_external"] and not _is_external_ip(ip) and sev != 1:
        return "NO", "IP interna del sitio"
    if _ip_in_exceptions(ip, pol["exceptions"]):
        return "NO", "en lista de excepciones"
    return "SI", f"severidad {sev}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--horas", type=int, default=24)
    ap.add_argument("--todo", action="store_true")
    args = ap.parse_args()

    desde = None if args.todo else datetime.now(timezone.utc) - timedelta(hours=args.horas)
    pol = _auto_block_policy()

    print("=" * 78)
    print("SIMULACRO — qué bloquearía Hunter con la política actual (sin tocar nada)")
    print("=" * 78)
    print(f"  autobloqueo : {pol['enabled']}")
    print(f"  min_severity: {pol['min_severity']} (menor número = más severo)")
    print(f"  solo externas: {pol['only_external']} | excepciones: {len(pol['exceptions'])}")
    print(f"  ventana     : {'todo el histórico' if args.todo else f'últimas {args.horas}h'}")
    print()

    bloquea: dict[str, dict] = {}
    no_bloquea: dict[str, int] = defaultdict(int)
    total = 0

    for ev in leer_alertas(desde):
        total += 1
        ip = (ev.get("src_ip") or "").strip()
        if not ip:
            continue
        alert = ev.get("alert") or {}
        firma = alert.get("signature") or ""
        sev = int(alert.get("severity") or 3)
        veredicto, motivo = decidir(ip, firma, sev, pol)
        if veredicto == "SI":
            reg = bloquea.setdefault(ip, {"n": 0, "firma": firma, "sev": sev})
            reg["n"] += 1
        else:
            no_bloquea[motivo] += 1

    print(f"Alertas analizadas: {total}")
    print(f"  NO se bloquean: {sum(no_bloquea.values())}")
    for motivo, n in sorted(no_bloquea.items(), key=lambda x: -x[1]):
        print(f"      {n:6}  {motivo}")
    print(f"  SE BLOQUEARÍAN: {len(bloquea)} IPs distintas")
    print()

    if bloquea:
        print(f"{'IP':17} {'SEV':4} {'VECES':6} FIRMA")
        print("-" * 78)
        for ip, d in sorted(bloquea.items(), key=lambda x: -x[1]["n"]):
            print(f"{ip:17} {d['sev']:<4} {d['n']:<6} {d['firma'][:44]}")
        print()

    # Semáforo final: ¿alguna de las que bloquearía es un servicio esencial?
    peligro = [(ip, servicio_critico(ip), d) for ip, d in bloquea.items() if servicio_critico(ip)]
    print("=" * 78)
    if peligro:
        print("🔴 NO ACTIVAR — bloquearía servicios esenciales:")
        for ip, srv, d in peligro:
            print(f"     {ip:17} {srv}  ← {d['firma'][:44]}")
        return 1
    print("🟢 SEGURO — ninguna de las IPs que bloquearía es un servicio esencial")
    print("   (DNS públicos, Google, Microsoft, Apple, Akamai, Cloudflare, Fastly)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
