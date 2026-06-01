"""
Ruta API para disparar backup manual desde el Dashboard.
"""
import sys
import os
from fastapi import APIRouter, HTTPException

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from scripts.backup_system import run_backup

router = APIRouter(tags=["backup"])


@router.post("/api/backup")
async def trigger_backup():
    """
    Dispara un backup manual: comprime la base de datos y la carpeta backend.
    Mantiene solo las últimas 5 copias.
    """
    try:
        ok, result = run_backup()
        if ok:
            return {"success": True, "path": result, "message": "Backup creado correctamente"}
        raise HTTPException(status_code=500, detail=result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
