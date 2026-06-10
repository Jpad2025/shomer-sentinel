"""
Módulo de Inventario estricto (assets) para SHOMER Suite.

- Base de datos: inventory.db en /storage/db/ (tabla assets). Rutas desde app.backend.db.
- Lógica repartida en app.api.inventory_*; aquí solo routers FastAPI.
"""

from __future__ import annotations

import io
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException
from fastapi.responses import JSONResponse, Response, StreamingResponse

from app.api.auth_api import get_current_user, require_admin
from app.api.inventory_asset_edit import sanitize_asset_updates, upsert_asset_row
from app.api.inventory_asset_report_pdf import build_asset_report_pdf_bytes
from app.api.inventory_assets_repo import (
    delete_asset_by_mac,
    fetch_all_assets_normalized,
    fetch_asset_by_ip_normalized,
    fetch_asset_by_mac_normalized,
)
from app.api.inventory_db_schema import ensure_assets_table, ensure_network_credentials
from app.api.inventory_discovery import (
    DISCOVERY_SCRIPT_PATH,
    SCANNER_PATH,
    build_deep_scan_environment,
    get_scan_status,
    kill_scan,
    run_inventory_deep_scan_background,
    run_inventory_quick_scan_background,
)
from app.api.inventory_excel_export import (
    render_global_client_excel_bytes,
    render_single_asset_excel_bytes,
    render_snapshot_archive_excel_bytes,
)
from app.api.inventory_label_pdf import build_asset_label_pdf, build_labels_sheet_pdf
from app.api.inventory_network_credentials import (
    fetch_network_credentials,
    save_network_credentials,
)
from app.api.inventory_remedies import load_remedies_json
from app.api.inventory_snapshots import (
    close_and_archive_inventory,
    list_snapshot_metadata,
    load_snapshot_assets,
)
from app.api.inventory_suricata_eve import enrich_assets_with_suricata_alerts
from app.backend.db import PATH_REPORTS, REMEDIES_JSON_PATH, get_connection_inventory

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/inventory", tags=["inventory_assets"])
export_router = APIRouter(prefix="/export", tags=["Export"])
snapshot_router = APIRouter(prefix="/snapshot", tags=["snapshots"])
rescan_router = APIRouter(prefix="/rescan", tags=["rescan"])


@router.post("/discovery_scan")
async def discovery_scan(
    background_tasks: BackgroundTasks,
    _user: Dict[str, Any] = Depends(get_current_user),
):
    if not os.path.isfile(DISCOVERY_SCRIPT_PATH):
        raise HTTPException(
            status_code=500,
            detail=f"Script de discovery no encontrado: {DISCOVERY_SCRIPT_PATH}",
        )
    status = get_scan_status()
    if status.get("running"):
        return JSONResponse(
            status_code=409,
            content={
                "success": False,
                "running": True,
                "message": f"Ya hay un escaneo activo ({status.get('mode','')}) — {status.get('elapsed_label','')} en progreso.",
            },
        )
    background_tasks.add_task(run_inventory_quick_scan_background)
    return JSONResponse(
        status_code=202,
        content={
            "success": True,
            "message": "Escaneo de red iniciado en segundo plano. Actualice la tabla en 1-2 min.",
            "background": True,
        },
    )


@router.post("/scan")
async def scan_inventory(
    background_tasks: BackgroundTasks,
    payload: Optional[Dict[str, Any]] = Body(default=None),
    _user: Dict[str, Any] = Depends(get_current_user),
):
    if not os.path.isfile(SCANNER_PATH):
        raise HTTPException(
            status_code=500,
            detail=f"scanner.py no encontrado en {SCANNER_PATH}",
        )
    status = get_scan_status()
    if status.get("running"):
        return JSONResponse(
            status_code=409,
            content={
                "success": False,
                "running": True,
                "message": f"Ya hay un escaneo activo ({status.get('mode','')}) — {status.get('elapsed_label','')} en progreso. Cancélalo primero.",
            },
        )
    env = build_deep_scan_environment(payload)
    background_tasks.add_task(run_inventory_deep_scan_background, env)
    return JSONResponse(
        status_code=202,
        content={
            "success": True,
            "message": "Escaneo iniciado en segundo plano. Actualice la tabla en 2-5 min.",
            "background": True,
        },
    )


@router.get("/scan/status")
async def scan_status(_user: Dict[str, Any] = Depends(get_current_user)):
    return JSONResponse(content=get_scan_status())


@router.post("/scan/cancel")
async def scan_cancel(_user: Dict[str, Any] = Depends(get_current_user)):
    killed = kill_scan()
    return JSONResponse(content={"success": True, "killed": killed})


@router.delete("/asset/{mac}")
async def delete_asset(
    mac: str,
    _admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    mac = (mac or "").strip()
    if not mac:
        raise HTTPException(status_code=400, detail="MAC requerida")
    with get_connection_inventory(timeout=30) as conn:
        n = delete_asset_by_mac(conn, mac)
    if n == 0:
        return {"success": True, "message": "El activo no existía", "deleted": False}
    return {"success": True, "message": "Activo eliminado", "deleted": True}


@router.get("/credentials")
async def get_credentials(_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    with get_connection_inventory(timeout=30) as conn:
        creds = fetch_network_credentials(conn)
    if creds is None:
        return {"success": True, "credentials": None}
    return {"success": True, "credentials": creds}


@router.post("/credentials")
async def save_credentials(
    payload: Dict[str, Any] = Body(...),
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    with get_connection_inventory(timeout=30) as conn:
        save_network_credentials(conn, payload)
    return {"success": True, "message": "Credenciales guardadas"}


@router.get("/list")
async def list_assets() -> Dict[str, Any]:
    with get_connection_inventory(timeout=30) as conn:
        assets = fetch_all_assets_normalized(conn)
    enrich_assets_with_suricata_alerts(assets)
    return {"success": True, "count": len(assets), "assets": assets}


@export_router.get("/inventory/excel/{ip}")
async def export_inventory_excel(ip: str) -> StreamingResponse:
    with get_connection_inventory(timeout=30) as conn:
        asset = fetch_asset_by_ip_normalized(conn, ip)
    if not asset:
        raise HTTPException(status_code=404, detail="Activo no encontrado")
    data = render_single_asset_excel_bytes(asset)
    filename = f"inventario_{ip.replace(':', '_')}.xlsx"
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename=\"{filename}\"'},
    )


@export_router.get("/asset/pdf/{ip}")
async def export_asset_pdf(ip: str) -> Response:
    with get_connection_inventory(timeout=30) as conn:
        a = fetch_asset_by_ip_normalized(conn, ip)
    if not a:
        raise HTTPException(status_code=404, detail="Activo no encontrado")
    pdf_bytes = build_asset_report_pdf_bytes(a)
    filename = f"activo_{ip.replace(':', '_')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename=\"{filename}\"'},
    )


@export_router.get("/labels/sheet")
async def export_labels_sheet_pdf() -> Response:
    """Hoja carta con 18 etiquetas (3×6) de 52×30 mm para todos los activos."""
    with get_connection_inventory(timeout=30) as conn:
        assets = fetch_all_assets_normalized(conn)
    if not assets:
        raise HTTPException(status_code=404, detail="No hay activos en el inventario")
    pdf_bytes = build_labels_sheet_pdf(assets)
    ts = datetime.utcnow().strftime("%Y-%m-%d_%H%M%S")
    filename = f"etiquetas_{ts}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@export_router.get("/asset/label/{mac}")
async def export_asset_label_pdf(mac: str) -> Response:
    from urllib.parse import unquote

    mac_key = unquote(mac).strip()
    with get_connection_inventory(timeout=30) as conn:
        a = fetch_asset_by_mac_normalized(conn, mac_key)
    if not a:
        raise HTTPException(status_code=404, detail="Activo no encontrado")
    try:
        pdf_bytes = build_asset_label_pdf(a)
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail="No se pudo generar la etiqueta (dependencias: qrcode, pillow, python-barcode). %s"
            % str(e)[:200],
        ) from e
    fn = "etiqueta_%s.pdf" % (mac_key.replace(":", "-").replace("/", "-") or "activo")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename=\"{fn}\"'},
    )


@export_router.get("/global/inventory/excel")
async def export_global_inventory_excel() -> Response:
    with get_connection_inventory(timeout=30) as conn:
        rows = fetch_all_assets_normalized(conn)
    content = render_global_client_excel_bytes(rows)
    ts = datetime.utcnow().strftime("%Y-%m-%d_%H%M%S")
    filename = f"inventario_global_{ts}.xlsx"
    try:
        os.makedirs(PATH_REPORTS, mode=0o755, exist_ok=True)
        archive_path = os.path.join(PATH_REPORTS, filename)
        with open(archive_path, "wb") as out:
            out.write(content)
    except OSError as e:
        logger.warning("No se pudo archivar Excel en %s: %s", PATH_REPORTS, e)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(content)),
            "X-Shomer-Reports-Path": os.path.join(PATH_REPORTS, filename),
        },
    )


@router.get("/remedies")
async def get_remedies(
    _admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    try:
        data = load_remedies_json(REMEDIES_JSON_PATH)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"remedies.json no encontrado en {REMEDIES_JSON_PATH}",
        )
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Error leyendo remedies.json: {e}") from e
    return {"success": True, "remedies": data}


@router.patch("/update/{mac}")
async def update_asset(
    mac: str,
    payload: Dict[str, Any] = Body(...),
    _admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    mac = (mac or "").strip()
    if not mac:
        raise HTTPException(status_code=400, detail="MAC requerida")
    updates = sanitize_asset_updates(payload)
    if not updates:
        return {"success": True, "message": "Nada que actualizar"}
    now_ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    updates["last_audit"] = now_ts
    with get_connection_inventory(timeout=30) as conn:
        ensure_network_credentials(conn)
        ensure_assets_table(conn)
        upsert_asset_row(conn, mac, updates)
    return {"success": True, "message": "Asset actualizado", "last_audit": now_ts}


# ── SNAPSHOTS ──────────────────────────────────────────────────────────────


@snapshot_router.post("/close")
async def close_and_archive(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="El campo 'name' es requerido")
    now = datetime.utcnow().isoformat()
    with get_connection_inventory(timeout=30) as conn:
        out = close_and_archive_inventory(conn, name, now)
    return {"success": True, **out}


@snapshot_router.get("/list")
async def list_snapshots() -> Dict[str, Any]:
    with get_connection_inventory(timeout=30) as conn:
        snapshots = list_snapshot_metadata(conn)
    return {"success": True, "snapshots": snapshots}


@rescan_router.post("/{mac}")
async def rescan_single_asset(
    mac: str,
    background_tasks: BackgroundTasks,
    payload: Optional[Dict[str, Any]] = Body(default=None),
    _user: Dict[str, Any] = Depends(get_current_user),
) -> JSONResponse:
    """Escaneo profundo para un único equipo por IP (desde el modal del inventario)."""
    from urllib.parse import unquote as _unquote
    mac_key = _unquote(mac).strip()
    ip = ""
    if payload and isinstance(payload, dict):
        ip = (payload.get("ip") or "").strip()
    if not ip:
        with get_connection_inventory(timeout=15) as conn:
            a = fetch_asset_by_mac_normalized(conn, mac_key)
        ip = (a or {}).get("ip", "").strip() if a else ""
    if not ip:
        raise HTTPException(status_code=400, detail="No se encontró IP para este activo")
    env = build_deep_scan_environment({"targets": ip})
    background_tasks.add_task(run_inventory_deep_scan_background, env)
    return JSONResponse(
        status_code=202,
        content={
            "success": True,
            "message": f"Escaneo profundo de {ip} iniciado. Actualiza en 2-3 min.",
            "ip": ip,
        },
    )


@snapshot_router.get("/{snapshot_id}/excel")
async def export_snapshot_excel(snapshot_id: int) -> Response:
    with get_connection_inventory(timeout=30) as conn:
        loaded = load_snapshot_assets(conn, snapshot_id)
    if not loaded:
        raise HTTPException(status_code=404, detail="Snapshot no encontrado")
    snap_name, snap_date, rows = loaded
    content = render_snapshot_archive_excel_bytes(rows)
    safe_name = snap_name.replace(" ", "_").replace("/", "-")[:50]
    filename = f"inventario_{safe_name}_{snap_date[:10]}.xlsx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(content)),
        },
    )
