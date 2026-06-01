# Este archivo hace que routes sea un paquete Python.
# Guardian (Shomer) es único: app.api.shomer. No hay router shomer aquí para evitar duplicados.
from . import devices, discovery, reboot, backup, inventory
__all__ = ["devices", "discovery", "reboot", "backup", "inventory"]