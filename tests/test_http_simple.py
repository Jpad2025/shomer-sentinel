"""
Prueba simple del gestor HTTP
"""
import sys
import os
sys.path.append('/opt/network_monitor/app/backend')

try:
    from router_http_manager import RouterHTTPManager
    print("✅ Módulo importado correctamente")
    
    # Crear instancia
    manager = RouterHTTPManager()
    print("✅ Instancia creada correctamente")
    
    # Mostrar métodos disponibles
    print("\nMétodos disponibles:")
    methods = [m for m in dir(manager) if not m.startswith('_') and callable(getattr(manager, m))]
    for method in methods:
        print(f"  - {method}")
    
except Exception as e:
    print(f"❌ Error: {str(e)}")
    import traceback
    traceback.print_exc()
