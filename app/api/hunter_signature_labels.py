"""Traduce firmas Suricata/ET a lenguaje claro para técnicos y panel."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

# (regex, title, detail, risk, action_tecnico)
_RULE_PATTERNS: List[Tuple[re.Pattern, str, str, str, str]] = [
    (
        re.compile(r"ET CINS.*Poor Reputation", re.I),
        "IP con mala reputación (lista CINS)",
        "Dirección reportada por inteligencia de amenazas por actividad maliciosa conocida.",
        "alto",
        "Shomer ya la bloqueó en el firewall. No requiere acción en el hotel si no hay quejas.",
    ),
    (
        re.compile(r"ET DROP.*Dshield", re.I),
        "IP en lista negra DShield",
        "Fuente asociada a ataques o escaneos reportados por la comunidad DShield.",
        "alto",
        "Bloqueo preventivo aplicado. Revisar solo si la IP es de un proveedor legítimo del hotel.",
    ),
    (
        re.compile(r"ET DROP.*Spamhaus", re.I),
        "IP en lista Spamhaus DROP",
        "Dirección conocida por spam, malware o abuso en internet.",
        "alto",
        "Bloqueo automático correcto. Sin acción en sitio salvo falso positivo confirmado.",
    ),
    (
        re.compile(r"ET DROP", re.I),
        "IP en lista negra de amenazas",
        "Tráfico desde una dirección marcada como peligrosa por reglas Emerging Threats.",
        "alto",
        "Shomer bloqueó el acceso. Monitorear; desbloquear solo si USB confirma falso positivo.",
    ),
    (
        re.compile(r"ET P2P.*eMule", re.I),
        "Tráfico P2P sospechoso (eMule)",
        "Un equipo de la red podría estar usando file-sharing P2P o estar comprometido.",
        "medio",
        "Identificar el equipo interno (.119 u otro) y revisar malware o uso no autorizado.",
    ),
    (
        re.compile(r"ET POLICY", re.I),
        "Política de seguridad de red",
        "Tráfico que viola una política (puerto, protocolo o uso no permitido).",
        "medio",
        "Revisar si es uso legítimo del hotel o equipo mal configurado.",
    ),
    (
        re.compile(r"ET SCAN", re.I),
        "Escaneo de puertos detectado",
        "Alguien en internet o en la red está probando puertos (reconocimiento).",
        "alto",
        "Si la IP es externa, el bloqueo es correcto. Si es interna, revisar el equipo origen.",
    ),
    (
        re.compile(r"ET EXPLOIT", re.I),
        "Intento de explotación",
        "Patrón de ataque conocido contra un servicio vulnerable.",
        "critico",
        "Riesgo real. Verificar que el servicio destino esté parcheado; mantener bloqueo.",
    ),
    (
        re.compile(r"ET MALWARE", re.I),
        "Tráfico asociado a malware",
        "Comunicación típica de software malicioso o botnet.",
        "critico",
        "Revisar equipos internos que hablen con esa IP; posible infección.",
    ),
    (
        re.compile(r"IKEv2|IKE", re.I),
        "Tráfico VPN IKEv2 en WAN",
        "Negociación VPN en el espejo de internet — suele ser operador móvil o VPN legítima.",
        "bajo",
        "En hotel suele ser falso positivo de operador. Shomer evalúa antes de bloquear.",
    ),
    (
        re.compile(r"SNMP", re.I),
        "Consulta SNMP en WAN",
        "Intento de lectura SNMP desde internet (escaneo o gestión remota).",
        "medio",
        "Normalmente tráfico externo no deseado. Bloqueo recomendado.",
    ),
]

_RISK_ICON = {
    "critico": "🔴",
    "alto": "🟠",
    "medio": "🟡",
    "bajo": "🟢",
    "info": "ℹ️",
}

_RISK_LABEL = {
    "critico": "CRÍTICO",
    "alto": "ALTO",
    "medio": "MEDIO",
    "bajo": "BAJO",
    "info": "INFO",
}


def humanize_hunter_signature(signature: Optional[str]) -> Dict[str, Any]:
    """Devuelve título, detalle, riesgo y guía para técnicos."""
    technical = (signature or "").strip()
    if not technical:
        return {
            "title": "Amenaza de red detectada",
            "detail": "Shomer detectó tráfico sospechoso hacia o desde internet.",
            "risk": "medio",
            "risk_label": "MEDIO",
            "risk_icon": "🟡",
            "action": "Confirmar en panel Hunter si el bloqueo es correcto.",
            "technical": "",
        }

    for pat, title, detail, risk, action in _RULE_PATTERNS:
        if pat.search(technical):
            return {
                "title": title,
                "detail": detail,
                "risk": risk,
                "risk_label": _RISK_LABEL.get(risk, "MEDIO"),
                "risk_icon": _RISK_ICON.get(risk, "🟡"),
                "action": action,
                "technical": technical,
            }

    # Genérico según prefijo ET
    if technical.upper().startswith("ET "):
        return {
            "title": "Amenaza detectada por Hunter",
            "detail": "Regla de seguridad Suricata activada en el tráfico WAN del hotel.",
            "risk": "medio",
            "risk_label": "MEDIO",
            "risk_icon": "🟡",
            "action": "Revisar en panel Hunter. Shomer bloquea si la política lo indica.",
            "technical": technical,
        }

    return {
        "title": "Evento de seguridad",
        "detail": technical[:200],
        "risk": "medio",
        "risk_label": "MEDIO",
        "risk_icon": "🟡",
        "action": "Confirmar en panel Hunter si requiere acción en sitio.",
        "technical": technical,
    }


def format_hunter_telegram_block(
    ip: str,
    signature: Optional[str],
    *,
    severity: int = 3,
    firewall_ok: bool = True,
    blocked_by: str = "auto",
    include_technical: bool = True,
) -> str:
    """Texto Telegram/HTML para bloqueos Hunter legibles."""
    h = humanize_hunter_signature(signature)
    sev_map = {1: "🔴 CRÍTICA", 2: "🟠 ALTA", 3: "🟡 MEDIA", 4: "⚪ BAJA"}
    sev_label = sev_map.get(int(severity or 3), "🟡 MEDIA")
    if blocked_by == "wazuh":
        header = "🛡️ <b>BLOQUEO (Wazuh → Shomer)</b>"
    else:
        header = "🚨 <b>BLOQUEO AUTOMÁTICO — Hunter</b>"

    fw_text = (
        "✅ Firewall del hotel: IP bloqueada"
        if firewall_ok
        else "⚠️ Solo registrado en panel — revisar firewall MikroTik"
    )
    lines = [
        header,
        f"{h['risk_icon']} <b>{h['risk_label']}</b> — {h['title']}",
        f"🌐 IP: <code>{ip}</code>",
        f"📋 <b>Qué significa:</b> {h['detail']}",
        f"👷 <b>Para el técnico:</b> {h['action']}",
        f"⚡ Severidad regla: {sev_label}",
        fw_text,
    ]
    if include_technical and h.get("technical"):
        tech = h["technical"][:180]
        lines.append(f"🔧 <i>Regla técnica: {tech}</i>")
    return "\n".join(lines)


def enrich_hunter_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Añade campos legibles a filas blocked_ips / incidents."""
    h = humanize_hunter_signature(row.get("alert_signature"))
    row["alert_human_title"] = h["title"]
    row["alert_human_detail"] = h["detail"]
    row["alert_human_risk"] = h["risk"]
    row["alert_human_risk_label"] = h["risk_label"]
    row["alert_human_action"] = h["action"]
    return row
