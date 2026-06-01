"""
Proxies HTTP desde el core (8000) hacia Tools (8001): Tracker, snapshots, Protector.
"""
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.api.auth_api import get_current_user, require_admin, verify_token
from app.api.shomer_common import (
    _tools_url,
    get_config,
    is_module_enabled,
    require_module,
)

router = APIRouter(tags=["Shomer Guardian"])


def _require_admin_request(request: Request) -> str:
    """
    Exige sesión admin para rutas sensibles proxied.
    Devuelve el token útil para forward al servicio downstream.
    """
    auth_h = request.headers.get("Authorization", "").strip()
    cookie_tok = request.cookies.get("access_token")
    token = ""
    if auth_h.lower().startswith("bearer "):
        token = auth_h.split(" ", 1)[1].strip()
    elif auth_h:
        token = auth_h
    elif cookie_tok:
        token = cookie_tok
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token requerido")
    if (payload.get("role") or "").lower() != "admin":
        raise HTTPException(status_code=403, detail="Se requiere rol admin")
    return token


@router.get("/tracker/assets")
async def tracker_assets(request: Request, user=Depends(get_current_user)):
    """Proxy: retorna activos del inventario desde puerto 8001."""
    require_module("tracker")
    token = request.headers.get("Authorization", "")
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                _tools_url("/inventory/list"),
                headers={"Authorization": token},
                timeout=10,
            )
        return JSONResponse(content=r.json(), status_code=r.status_code)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/tracker/scan")
async def tracker_scan(request: Request, user=Depends(get_current_user)):
    """Proxy: lanza discovery_scan en 8001 con subnet leída de system_state."""
    token = request.headers.get("Authorization", "")
    subnet = get_config("tracker.subnets", [])
    subnet = subnet[0] if isinstance(subnet, list) and subnet else get_config("base.subnet", "")
    if not subnet:
        raise HTTPException(
            status_code=400,
            detail="Configura la subnet del Tracker en Configuración de Red",
        )
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                _tools_url("/inventory/discovery_scan"),
                json={"subnet": subnet},
                headers={"Authorization": token, "Content-Type": "application/json"},
                timeout=15,
            )
        return JSONResponse(content=r.json(), status_code=r.status_code)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.patch("/tracker/asset/{mac}")
async def tracker_update_asset(mac: str, request: Request):
    """Proxy: actualiza un activo en 8001."""
    token = request.headers.get("Authorization", "")
    body = await request.json()
    try:
        async with httpx.AsyncClient() as client:
            r = await client.patch(
                _tools_url(f"/inventory/update/{mac}"),
                json=body,
                headers={"Authorization": token, "Content-Type": "application/json"},
                timeout=10,
            )
        return JSONResponse(content=r.json(), status_code=r.status_code)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/snapshot/close")
async def proxy_snapshot_close(request: Request, user=Depends(require_admin)):
    """Proxy: archiva inventario actual como snapshot y limpia tabla assets."""
    token = request.headers.get("Authorization", "")
    body = await request.json()
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                _tools_url("/snapshot/close"),
                json=body,
                headers={"Authorization": token},
                timeout=30,
            )
        return JSONResponse(content=r.json(), status_code=r.status_code)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/snapshots")
async def proxy_snapshots_list(request: Request, user=Depends(get_current_user)):
    """Proxy: lista todos los snapshots archivados."""
    token = request.headers.get("Authorization", "")
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                _tools_url("/snapshot/list"),
                headers={"Authorization": token},
                timeout=10,
            )
        return JSONResponse(content=r.json(), status_code=r.status_code)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/snapshot/{snapshot_id}/excel")
async def proxy_snapshot_excel(snapshot_id: int, request: Request):
    """Proxy: descarga Excel de un snapshot archivado."""
    from fastapi.responses import Response as FastAPIResponse

    token = request.headers.get("Authorization", "")
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                _tools_url(f"/snapshot/{snapshot_id}/excel"),
                headers={"Authorization": token},
                timeout=60,
            )
        return FastAPIResponse(
            content=r.content,
            status_code=r.status_code,
            media_type=r.headers.get(
                "content-type",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
            headers={
                "Content-Disposition": r.headers.get(
                    "content-disposition",
                    f'attachment; filename="snapshot_{snapshot_id}.xlsx"',
                )
            },
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.delete("/tracker/asset/{mac}")
async def tracker_delete_asset(mac: str, request: Request):
    """Proxy: elimina un activo del inventario en 8001."""
    token = request.headers.get("Authorization", "")
    try:
        async with httpx.AsyncClient() as client:
            r = await client.delete(
                _tools_url(f"/inventory/asset/{mac}"),
                headers={"Authorization": token},
                timeout=10,
            )
        return JSONResponse(content=r.json(), status_code=r.status_code)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/tracker/deep_scan")
async def tracker_deep_scan(request: Request, user=Depends(get_current_user)):
    """
    Proxy: lanza escaneo profundo (nmap -sV -O + WMI/SSH/SNMP)
    en segundo plano via puerto 8001.
    Lee subnet de system_state si no viene en el payload.
    """
    token = request.headers.get("Authorization", "")
    try:
        body = await request.json()
    except Exception:
        body = {}

    targets = body.get("targets") or body.get("subnet") or ""
    if not targets:
        subnets = get_config("tracker.subnets", [])
        targets = subnets[0] if subnets else get_config("base.subnet", "")
    if not targets:
        raise HTTPException(
            status_code=400,
            detail="Configura la subnet del Tracker en Configuración de Red",
        )
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                _tools_url("/inventory/scan"),
                json={"targets": targets},
                headers={
                    "Authorization": token,
                    "Content-Type": "application/json",
                },
                timeout=15,
            )
        return JSONResponse(content=r.json(), status_code=r.status_code)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/tracker/credentials")
async def tracker_get_credentials(request: Request, user=Depends(get_current_user)):
    """Proxy: lee credenciales globales de red desde 8001."""
    token = request.headers.get("Authorization", "")
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                _tools_url("/inventory/credentials"),
                headers={"Authorization": token},
                timeout=10,
            )
        return JSONResponse(content=r.json(), status_code=r.status_code)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/tracker/credentials")
async def tracker_save_credentials(request: Request, user=Depends(get_current_user)):
    """Proxy: guarda credenciales globales de red en 8001."""
    token = request.headers.get("Authorization", "")
    body = await request.json()
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                _tools_url("/inventory/credentials"),
                json=body,
                headers={
                    "Authorization": token,
                    "Content-Type": "application/json",
                },
                timeout=10,
            )
        return JSONResponse(content=r.json(), status_code=r.status_code)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/tracker/rescan/{mac}")
async def tracker_rescan_asset(mac: str, request: Request, user=Depends(get_current_user)):
    """
    Proxy: rescanea un equipo individual usando credenciales override o globales.
    """
    token = request.headers.get("Authorization", "")
    try:
        body = await request.json()
    except Exception:
        body = {}

    ip = body.get("ip", "")
    if not ip:
        raise HTTPException(status_code=400, detail="ip requerida")

    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                _tools_url("/inventory/scan"),
                json={"targets": ip},
                headers={
                    "Authorization": token,
                    "Content-Type": "application/json",
                },
                timeout=15,
            )
        return JSONResponse(content=r.json(), status_code=r.status_code)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/tracker/export/excel")
async def tracker_export_excel(request: Request, user=Depends(get_current_user)):
    require_module("tracker")
    from fastapi.responses import Response as FastAPIResponse

    token = request.headers.get("Authorization", "")
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                _tools_url("/export/global/inventory/excel"),
                headers={"Authorization": token},
                timeout=60,
            )
        return FastAPIResponse(
            content=r.content,
            status_code=r.status_code,
            media_type=r.headers.get(
                "content-type",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
            headers={
                "Content-Disposition": r.headers.get(
                    "content-disposition", "attachment; filename=inventario_global.xlsx"
                )
            },
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/tracker/export/labels/sheet")
async def tracker_export_labels_sheet(request: Request, user=Depends(get_current_user)):
    """Proxy: PDF hoja carta con 18 etiquetas de todos los activos (puerto 8001)."""
    require_module("tracker")
    from fastapi.responses import Response as FastAPIResponse

    token = request.headers.get("Authorization", "")
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                _tools_url("/export/labels/sheet"),
                headers={"Authorization": token},
                timeout=60,
            )
        return FastAPIResponse(
            content=r.content,
            status_code=r.status_code,
            media_type=r.headers.get("content-type", "application/pdf"),
            headers={
                "Content-Disposition": r.headers.get(
                    "content-disposition",
                    'attachment; filename="etiquetas.pdf"',
                )
            },
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/tracker/export/asset/label/{mac}")
async def tracker_export_asset_label(mac: str, request: Request, user=Depends(get_current_user)):
    """Proxy: PDF etiqueta QR + código de barras por MAC (puerto 8001)."""
    require_module("tracker")
    from urllib.parse import quote
    from fastapi.responses import Response as FastAPIResponse

    token = request.headers.get("Authorization", "")
    path_mac = quote(mac, safe="")
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                _tools_url(f"/export/asset/label/{path_mac}"),
                headers={"Authorization": token},
                timeout=45,
            )
        return FastAPIResponse(
            content=r.content,
            status_code=r.status_code,
            media_type=r.headers.get("content-type", "application/pdf"),
            headers={
                "Content-Disposition": r.headers.get(
                    "content-disposition",
                    'attachment; filename="etiqueta.pdf"',
                )
            },
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


async def _proxy_backups(request: Request, path: str, method: str = "GET", timeout: int = 30):
    """Helper genérico para proxear peticiones /backups/* a puerto 8001."""
    if not is_module_enabled("protector"):
        raise HTTPException(
            status_code=403,
            detail="Módulo Protector no habilitado en esta instalación",
        )
    token = _require_admin_request(request)
    headers = {"Authorization": f"Bearer {token}"}
    cookie = request.headers.get("cookie", "")
    if cookie:
        headers["Cookie"] = cookie
    body = None
    if method in ("POST", "PATCH", "PUT"):
        try:
            body = await request.json()
            headers["Content-Type"] = "application/json"
        except Exception:
            body = None
    try:
        async with httpx.AsyncClient() as client:
            r = await client.request(
                method,
                _tools_url(path),
                json=body,
                headers=headers,
                timeout=timeout,
            )
        return JSONResponse(content=r.json(), status_code=r.status_code)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Protector offline: {e}")


@router.get("/backups/snapshots")
async def proxy_backups_snapshots(request: Request, user=Depends(get_current_user)):
    return await _proxy_backups(request, "/backups/snapshots")


@router.get("/backups/health")
async def proxy_backups_health(request: Request):
    return await _proxy_backups(request, "/backups/health")


@router.post("/backups/run")
async def proxy_backups_run(request: Request, user=Depends(get_current_user)):
    return await _proxy_backups(request, "/backups/run", method="POST", timeout=120)


@router.post("/backups/run_local")
async def proxy_backups_run_local(request: Request, user=Depends(get_current_user)):
    return await _proxy_backups(request, "/backups/run_local", method="POST", timeout=120)


@router.post("/backups/sync_cloud")
async def proxy_backups_sync_cloud(request: Request, user=Depends(get_current_user)):
    return await _proxy_backups(request, "/backups/sync_cloud", method="POST", timeout=120)


@router.get("/backups/devices")
async def proxy_backups_devices_list(request: Request):
    return await _proxy_backups(request, "/backups/devices")


@router.get("/backups/devices/{device_id}")
async def proxy_backups_devices_get(device_id: int, request: Request):
    return await _proxy_backups(request, f"/backups/devices/{device_id}")


@router.post("/backups/devices")
async def proxy_backups_devices_create(request: Request, user=Depends(get_current_user)):
    return await _proxy_backups(request, "/backups/devices", method="POST")


@router.patch("/backups/devices/{device_id}")
async def proxy_backups_devices_patch(device_id: int, request: Request):
    return await _proxy_backups(request, f"/backups/devices/{device_id}", method="PATCH", timeout=30)


@router.post("/backups/devices/test")
async def proxy_backups_devices_test(request: Request, user=Depends(get_current_user)):
    return await _proxy_backups(request, "/backups/devices/test", method="POST", timeout=20)


@router.delete("/backups/devices/{device_id}")
async def proxy_backups_devices_delete(device_id: int, request: Request):
    return await _proxy_backups(request, f"/backups/devices/{device_id}", method="DELETE")


@router.post("/backups/devices/backup_now")
async def proxy_backups_now(request: Request, user=Depends(get_current_user)):
    return await _proxy_backups(request, "/backups/devices/backup_now", method="POST", timeout=300)


@router.post("/backups/devices/backup_all")
async def proxy_backups_all(request: Request, user=Depends(get_current_user)):
    return await _proxy_backups(request, "/backups/devices/backup_all", method="POST", timeout=600)


@router.get("/backups/b2config")
async def proxy_backups_b2config_get(request: Request):
    return await _proxy_backups(request, "/backups/b2config")


@router.post("/backups/b2config")
async def proxy_backups_b2config_save(request: Request, user=Depends(get_current_user)):
    return await _proxy_backups(request, "/backups/b2config", method="POST")


@router.post("/backups/b2/test")
async def proxy_backups_b2_test(request: Request, user=Depends(get_current_user)):
    return await _proxy_backups(request, "/backups/b2/test", method="POST", timeout=60)


@router.get("/backups/b2/snapshots")
async def proxy_backups_b2_snapshots(request: Request, user=Depends(get_current_user)):
    return await _proxy_backups(request, "/backups/b2/snapshots", timeout=90)


@router.get("/backups/restore/{snapshot_id}/download")
async def proxy_backups_restore_download(snapshot_id: str, request: Request):
    if not is_module_enabled("protector"):
        raise HTTPException(status_code=403, detail="Módulo Protector no habilitado en esta instalación")
    token = _require_admin_request(request)
    headers = {"Authorization": f"Bearer {token}"}
    try:
        client = httpx.AsyncClient(timeout=600)
        r = await client.get(_tools_url(f"/backups/restore/{snapshot_id}/download"), headers=headers)
        if r.status_code != 200:
            await client.aclose()
            return JSONResponse(content=r.json(), status_code=r.status_code)
        cd = r.headers.get("content-disposition", f'attachment; filename="restore_{snapshot_id[:8]}.zip"')
        return StreamingResponse(
            r.aiter_bytes(),
            status_code=200,
            media_type="application/zip",
            headers={"Content-Disposition": cd},
            background=None,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Protector offline: {e}")


@router.post("/backups/b2/restore/{snapshot_id}")
async def proxy_backups_b2_restore(snapshot_id: str, request: Request, user=Depends(get_current_user)):
    return await _proxy_backups(request, f"/backups/b2/restore/{snapshot_id}", method="POST", timeout=3600)


@router.post("/backups/restore/{snapshot_id}")
async def proxy_backups_restore(snapshot_id: str, request: Request, user=Depends(get_current_user)):
    return await _proxy_backups(request, f"/backups/restore/{snapshot_id}", method="POST", timeout=300)


@router.delete("/backups/snapshot/{snapshot_id}")
async def proxy_backups_snapshot_delete(snapshot_id: str, request: Request):
    return await _proxy_backups(request, f"/backups/snapshot/{snapshot_id}", method="DELETE", timeout=60)


@router.get("/backups/scheduler/status")
async def proxy_backups_scheduler_status(request: Request):
    return await _proxy_backups(request, "/backups/scheduler/status")


# ── Drill — R3 ────────────────────────────────────────────────────────────────

@router.post("/drill/run")
async def proxy_drill_run(request: Request, user=Depends(get_current_user)):
    return await _proxy_backups(request, "/drill/run", method="POST", timeout=300)

@router.get("/drill/status")
async def proxy_drill_status(request: Request):
    return await _proxy_backups(request, "/drill/status")

@router.get("/drill/history")
async def proxy_drill_history(request: Request):
    return await _proxy_backups(request, "/drill/history")

@router.get("/drill/history/csv")
async def proxy_drill_history_csv(request: Request):
    token = _require_admin_request(request)
    headers = {"Authorization": f"Bearer {token}"}
    cookie = request.headers.get("cookie", "")
    if cookie:
        headers["Cookie"] = cookie
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(_tools_url("/drill/history/csv"), headers=headers)
    cd = r.headers.get("content-disposition", "attachment; filename=drill_history.csv")
    return StreamingResponse(iter([r.content]), status_code=r.status_code,
        media_type="text/csv", headers={"Content-Disposition": cd})


# ── Reports — R1 ──────────────────────────────────────────────────────────────

@router.post("/reports/generate")
async def proxy_reports_generate(request: Request, user=Depends(get_current_user)):
    return await _proxy_backups(request, "/reports/generate", method="POST", timeout=120)

@router.post("/reports/generate/now")
async def proxy_reports_generate_now(request: Request, user=Depends(get_current_user)):
    return await _proxy_backups(request, "/reports/generate/now", method="POST", timeout=120)

@router.get("/reports/list")
async def proxy_reports_list(request: Request):
    return await _proxy_backups(request, "/reports/list")

@router.get("/reports/download/{filename}")
async def proxy_reports_download(filename: str, request: Request):
    token = _require_admin_request(request)
    headers = {"Authorization": f"Bearer {token}"}
    cookie = request.headers.get("cookie", "")
    if cookie:
        headers["Cookie"] = cookie
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(_tools_url(f"/reports/download/{filename}"), headers=headers)
    cd = r.headers.get("content-disposition", f"attachment; filename={filename}")
    return StreamingResponse(iter([r.content]), status_code=r.status_code,
        media_type="application/pdf", headers={"Content-Disposition": cd})
