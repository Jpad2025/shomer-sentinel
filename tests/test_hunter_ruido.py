"""Hunter no debe autobloquear reglas informativas ni anomalías de protocolo.

Caso real (8 sep 2026, Hotel Ópera): con hunter.auto_block_min_severity=3 se
bloquearon 22 IPs por reglas que no describen un ataque — Google por "STREAM
ESTABLISHED SYNACK resend", Canonical por "HTTP unable to match response", y
varias por STUN, que es como funciona cualquier videollamada. Eso cortó
internet legítimo del hotel; el proveedor deshabilitó la regla de firewall de
Shomer y el puerto del espejo SPAN para recuperar el servicio, dejando a Hunter
ciego.

El umbral de severidad no basta: la misma firma puede llegar con otra severidad
según la fuente (Suricata directo vs Wazuh), así que el filtro va por lo que la
regla dice.
"""
import unittest

from app.api.casador_blocking import _firma_es_ruido


# Firmas exactas tomadas de blocked_ips en producción.
RUIDO_REAL = [
    "ET INFO Session Traversal Utilities for NAT (STUN Binding Response)",
    "SURICATA HTTP unable to match response to request",
    "SURICATA STREAM ESTABLISHED SYNACK resend",
    "SURICATA STREAM ESTABLISHED SYNACK resend with different ACK",
    "SURICATA TCP option invalid length",
    "SURICATA IKEv2 weak cryptographic parameters (Diffie-Hellman)",
    "ET POLICY Possible External IP Lookup",
]

# Amenazas reales que SÍ deben seguir bloqueándose.
AMENAZAS_REALES = [
    "ET DROP Spamhaus DROP Listed Traffic Inbound group 43",
    "ET CINS Active Threat Intelligence Poor Reputation IP group 51",
    "ET DROP Dshield Block Listed Source group 1",
    "ET SCAN Zmap User-Agent (Inbound)",
    "GPL SNMP public access udp",
    "GPL VOIP SIP INVITE message flooding",
    "ET EXPLOIT Possible CVE-2021-44228 Log4j RCE",
]


class TestFirmasDeRuido(unittest.TestCase):
    def test_ruido_no_bloquea(self):
        for firma in RUIDO_REAL:
            with self.subTest(firma=firma):
                self.assertTrue(
                    _firma_es_ruido(firma),
                    f"esta firma no justifica cortar tráfico: {firma}",
                )

    def test_amenazas_siguen_bloqueando(self):
        for firma in AMENAZAS_REALES:
            with self.subTest(firma=firma):
                self.assertFalse(
                    _firma_es_ruido(firma),
                    f"esta SÍ es una amenaza y debe bloquearse: {firma}",
                )

    def test_firma_vacia_no_es_ruido(self):
        """Sin firma no se puede afirmar que sea ruido: decide la severidad."""
        for vacia in ("", None, "   "):
            self.assertEqual(_firma_es_ruido(vacia), "")

    def test_es_insensible_a_mayusculas(self):
        self.assertTrue(_firma_es_ruido("et info session traversal utilities"))


class TestPollerRespetaElFiltro(unittest.TestCase):
    def test_should_auto_block_descarta_ruido(self):
        from app.api.casador_autoblock_poller import _should_auto_block

        policy = {
            "enabled": True, "min_severity": 2,
            "only_external": True, "exceptions": [],
        }
        alerta_ruido = {
            "src_ip": "142.250.218.197",  # Google, el caso real
            "severity": 2,                # aunque llegue como severidad alta
            "alert_signature": "SURICATA STREAM ESTABLISHED SYNACK resend",
        }
        self.assertFalse(
            _should_auto_block(alerta_ruido, policy),
            "una anomalía de protocolo no debe bloquear ni con severidad 2",
        )

    def test_should_auto_block_acepta_amenaza(self):
        from app.api.casador_autoblock_poller import _should_auto_block

        policy = {
            "enabled": True, "min_severity": 2,
            "only_external": True, "exceptions": [],
        }
        amenaza = {
            "src_ip": "185.220.101.1",
            "severity": 2,
            "alert_signature": "ET DROP Spamhaus DROP Listed Traffic Inbound group 43",
        }
        self.assertTrue(_should_auto_block(amenaza, policy))


if __name__ == "__main__":
    unittest.main()
