#!/usr/bin/env python3
"""Compara el código de toda la flota contra el maestro y dice qué está fuera de sitio.

Por qué existe (11-12 sep 2026): nueve archivos del core llevaban días
corriendo en producción **sin commitear**. No los detectó nadie porque nada los
buscaba: el servicio funcionaba, las pruebas pasaban y `git log` se veía
limpio. Se habrían perdido en la siguiente reinstalación, y los tres labs nunca
los tuvieron.

Dos fallas distintas, y las dos silenciosas:

1. **Código vivo sin commitear.** Se edita en el servidor para arreglar algo
   urgente y queda ahí. Git no avisa, el servicio tampoco.
2. **Deriva contra el maestro.** Un sitio se queda atrás porque la sincronización
   del core se hace a mano, tecleando la lista de archivos en cada rsync: lo
   que no se teclea, no viaja.

Comparar `git log` entre sitios NO sirve para lo segundo: cada sitio reconcilia
con commits propios, así que los hashes difieren siempre aunque el contenido
sea idéntico. Acá se compara el **contenido** archivo por archivo.

Uso:
    tools/fleet_estado.py                 # revisa la flota entera
    tools/fleet_estado.py --json          # salida para otro programa
    tools/fleet_estado.py shomer245       # solo ese host

Devuelve 0 si todo está consistente y 1 si hay algo que revisar, para poder
usarlo como guardia antes de sincronizar o desplegar.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

# Los dos repositorios del producto. Configurable por si una instalación los
# pone en otro lado.
REPOS = [
    r for r in os.environ.get(
        "SHOMER_REPOS", "/opt/network_monitor:/storage/shomer-agent"
    ).split(":") if r.strip()
]

# La lista de la flota es la misma que usa fleet_sync.sh: un alias SSH por
# línea. Se busca en varias rutas para no clavar ninguna.
CANDIDATOS_HOSTS = [
    os.environ.get("SHOMER_FLEET_HOSTS", ""),
    "/etc/shomer/fleet_hosts.txt",
    "/storage/shomer-agent/tools/fleet_hosts.txt",
]

# Archivos que es CORRECTO que difieran entre sitios: son de cada instalación,
# no del producto. Si algo de acá apareciera igual en todos los hoteles sería
# el error contrario.
PROPIOS_DEL_SITIO = (
    ".env", "SITE.md", "servers.txt", "fleet_hosts.txt", "fleet_sync.log",
    "devices.json",
)
SUFIJOS_IGNORADOS = (".db", ".pyc", ".pyo", ".log", ".sqlite", ".sqlite3")
DIRS_IGNORADOS = (
    "__pycache__/", "venv/", ".venv/", "data/", "logs/", ".pytest_cache/",
    # Código muerto que ya no se despliega: está en el maestro por historia,
    # nunca llegó a los labs y no debe ensuciar el informe cada día.
    "_archivo_obsoleto/",
)

TIMEOUT_SSH = 90


def ruta_hosts() -> str:
    for c in CANDIDATOS_HOSTS:
        if c and Path(c).is_file():
            return c
    return ""


def leer_hosts(ruta: str):
    if not ruta:
        return []
    out = []
    for linea in Path(ruta).read_text(encoding="utf-8", errors="replace").splitlines():
        linea = linea.strip()
        if linea and not linea.startswith("#"):
            out.append(linea)
    return out


def es_del_sitio(ruta: str) -> bool:
    """True si es correcto que ese archivo difiera entre instalaciones."""
    if any(ruta.startswith(d) or ("/" + d) in ruta for d in DIRS_IGNORADOS):
        return True
    if ruta.endswith(SUFIJOS_IGNORADOS):
        return True
    nombre = ruta.rsplit("/", 1)[-1]
    return nombre in PROPIOS_DEL_SITIO


# Un solo comando por host: HEAD, archivos sin commitear y el hash de cada
# archivo versionado. Se lanza una vez por repositorio para no abrir una
# sesión SSH por archivo.
GUION = r"""
cd '{repo}' 2>/dev/null || { echo "REPO_AUSENTE"; exit 0; }
echo "HEAD $(git rev-parse --short HEAD 2>/dev/null)"
git status --porcelain 2>/dev/null | sed 's/^/SUCIO /'
git ls-files -z 2>/dev/null | xargs -0 md5sum 2>/dev/null | sed 's/^/HASH /'
"""


def _corre(argv, guion, timeout=TIMEOUT_SSH):
    """El guion va por la entrada estándar, nunca dentro de la línea de comando.

    Metido como argumento, el `$(git rev-parse ...)` lo expandía el shell
    LOCAL antes de viajar, y cada sitio respondía con datos del maestro: la
    comparación daba "al día" siempre. Por stdin no lo toca nadie hasta llegar.
    """
    try:
        r = subprocess.run(argv, input=guion, capture_output=True, text=True,
                           timeout=timeout)
        return r.stdout
    except subprocess.TimeoutExpired:
        return "TIMEOUT"
    except OSError as e:
        return "ERROR %s" % e


def inspeccionar(host: str, repo: str) -> dict:
    """host vacío = el maestro, acá mismo."""
    guion = GUION.replace("{repo}", repo)
    argv = (["ssh", "-o", "ConnectTimeout=10", "-o", "BatchMode=yes", host, "bash", "-s"]
            if host else ["bash", "-s"])
    salida = _corre(argv, guion)
    if salida.startswith("TIMEOUT") or salida.startswith("ERROR"):
        return {"alcanzable": False, "detalle": salida.strip()[:200]}
    if "REPO_AUSENTE" in salida:
        return {"alcanzable": True, "presente": False}

    head, sucios, hashes = "", [], {}
    for linea in salida.splitlines():
        if linea.startswith("HEAD "):
            head = linea[5:].strip()
        elif linea.startswith("SUCIO "):
            resto = linea[6:]
            ruta = resto[3:].strip() if len(resto) > 3 else resto.strip()
            # Un renombrado se reporta "viejo -> nuevo": interesa el destino.
            ruta = ruta.split(" -> ")[-1].strip().strip('"')
            if ruta and not es_del_sitio(ruta):
                sucios.append(ruta)
        elif linea.startswith("HASH "):
            partes = linea[5:].split(None, 1)
            if len(partes) == 2:
                ruta = partes[1].strip()
                if not es_del_sitio(ruta):
                    hashes[ruta] = partes[0]
    return {
        "alcanzable": True, "presente": True, "head": head,
        "sin_commitear": sorted(set(sucios)), "hashes": hashes,
    }


def comparar(maestro: dict, sitio: dict) -> dict:
    """Qué le falta, qué difiere y qué le sobra a un sitio contra el maestro."""
    if not sitio.get("presente"):
        return {}
    hm, hs = maestro.get("hashes", {}), sitio.get("hashes", {})
    return {
        "faltan": sorted(set(hm) - set(hs)),
        "difieren": sorted(r for r in set(hm) & set(hs) if hm[r] != hs[r]),
        "sobran": sorted(set(hs) - set(hm)),
    }


def revisar(hosts, repos) -> dict:
    resultado = {"repos": {}, "consistente": True}
    for repo in repos:
        maestro = inspeccionar("", repo)
        datos = {"maestro": {
            "head": maestro.get("head", ""),
            "sin_commitear": maestro.get("sin_commitear", []),
            "versionados": len(maestro.get("hashes", {})),
        }, "sitios": {}}
        if maestro.get("sin_commitear"):
            resultado["consistente"] = False
        for h in hosts:
            s = inspeccionar(h, repo)
            fila = {
                "alcanzable": s.get("alcanzable", False),
                "presente": s.get("presente", False),
                "head": s.get("head", ""),
                "sin_commitear": s.get("sin_commitear", []),
            }
            fila.update(comparar(maestro, s))
            if (not fila["alcanzable"] or not fila["presente"]
                    or fila["sin_commitear"] or fila.get("faltan")
                    or fila.get("difieren")):
                resultado["consistente"] = False
            datos["sitios"][h] = fila
        resultado["repos"][repo] = datos
    return resultado


def _lista(rutas, maximo=6):
    if len(rutas) <= maximo:
        return ", ".join(rutas)
    return ", ".join(rutas[:maximo]) + " y %d más" % (len(rutas) - maximo)


def redactar(r: dict) -> str:
    """En español llano: qué pasa y qué hacer, sin jerga de git."""
    lineas = []
    for repo, datos in r["repos"].items():
        nombre = repo.rstrip("/").rsplit("/", 1)[-1]
        m = datos["maestro"]
        lineas.append("── %s (%d archivos versionados) ──" % (nombre, m["versionados"]))
        if m["sin_commitear"]:
            lineas.append(
                "  MAESTRO: %d archivo(s) corriendo sin commitear — se pierden en la\n"
                "  próxima reinstalación y ningún otro sitio los tiene: %s"
                % (len(m["sin_commitear"]), _lista(m["sin_commitear"])))
        for host, s in datos["sitios"].items():
            if not s["alcanzable"]:
                lineas.append("  %s: no responde" % host)
                continue
            if not s["presente"]:
                lineas.append("  %s: no tiene este repositorio" % host)
                continue
            problemas = []
            if s["sin_commitear"]:
                problemas.append("%d sin commitear (%s)"
                                 % (len(s["sin_commitear"]), _lista(s["sin_commitear"], 3)))
            if s.get("faltan"):
                problemas.append("le faltan %d archivo(s): %s"
                                 % (len(s["faltan"]), _lista(s["faltan"], 3)))
            if s.get("difieren"):
                problemas.append("%d archivo(s) con contenido distinto: %s"
                                 % (len(s["difieren"]), _lista(s["difieren"], 3)))
            if problemas:
                lineas.append("  %s: %s" % (host, "; ".join(problemas)))
            else:
                lineas.append("  %s: al día" % host)
    if r["consistente"]:
        lineas.append("\nToda la flota tiene el mismo código y nada quedó fuera de git.")
    else:
        lineas.append("\nHay diferencias: revisar arriba antes de dar la flota por consolidada.")
    return "\n".join(lineas)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("hosts", nargs="*", help="hosts a revisar (por defecto, toda la flota)")
    ap.add_argument("--json", action="store_true", help="salida en JSON")
    ap.add_argument("--repos", default="", help="repositorios separados por ':'")
    args = ap.parse_args()

    repos = [x for x in args.repos.split(":") if x] or REPOS
    hosts = args.hosts or leer_hosts(ruta_hosts())
    if not hosts:
        print("Sin hosts que revisar: falta la lista de la flota (%s)."
              % " o ".join(x for x in CANDIDATOS_HOSTS if x), file=sys.stderr)
        return 2

    r = revisar(hosts, repos)
    print(json.dumps(r, indent=1, ensure_ascii=False) if args.json else redactar(r))
    return 0 if r["consistente"] else 1


if __name__ == "__main__":
    sys.exit(main())
