#!/usr/bin/env python3
from app.scripts.advanced_recovery import recover_device

# Definir dispositivo de prueba
device = {
    "id": 1,
    "name": "TP-Link Archer C54",
    "ip_address": "192.168.1.200",
    "mac_address": "00:00:00:00:00:00",
    "brand": "tplink",
    "ssh_user": "admin",
    "ssh_password": "Usbing08*"
}

# Intentar recuperación
print("Iniciando recuperación del router...")
success, message = recover_device(device)

# Mostrar resultado
if success:
    print(f"✅ Recuperación exitosa: {message}")
else:
    print(f"❌ Recuperación fallida: {message}")
