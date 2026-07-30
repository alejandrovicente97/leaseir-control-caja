# -*- coding: utf-8 -*-
"""
============================================================================
 LEASEIR - Lector del calendario de cobros de Eli desde Google Drive
============================================================================
 El fichero de Eli vive en Drive como .xlsx subido:
   https://docs.google.com/spreadsheets/d/1EmO9WHz-ewB8objYRnAvoQ2ZBkhnzAbR

 Se lee con una cuenta de servicio de Google Cloud, no con tu usuario: asi el
 GitHub Action funciona de madrugada sin que nadie inicie sesion.

 Credencial: variable de entorno GOOGLE_SERVICE_ACCOUNT_JSON con el JSON de la
 cuenta de servicio (en GitHub va en Secrets, nunca en el repo).

 Requisitos:  pip install google-auth requests
============================================================================
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ID_SHEET_ELI = "1EmO9WHz-ewB8objYRnAvoQ2ZBkhnzAbR"
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _credencial():
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw:
        ruta = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
        if ruta and Path(ruta).exists():
            raw = Path(ruta).read_text(encoding="utf-8")
    if not raw:
        raise SystemExit(
            "No hay credencial de Google.\n"
            "  Define GOOGLE_SERVICE_ACCOUNT_JSON con el JSON de la cuenta de servicio,\n"
            "  o GOOGLE_APPLICATION_CREDENTIALS apuntando al fichero."
        )
    try:
        info = json.loads(raw)
    except json.JSONDecodeError as e:
        raise SystemExit(f"El JSON de la cuenta de servicio no es valido: {e}")

    try:
        from google.oauth2 import service_account
    except ImportError:
        raise SystemExit("Falta google-auth.  Ejecuta:  pip install google-auth")

    return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)


def descargar_publico(file_id: str = ID_SHEET_ELI,
                      destino: Path = Path("calendario_eli.xlsx")) -> Path | None:
    """
    Via rapida: si el fichero esta compartido como "cualquiera con el enlace",
    se baja con una URL normal y corriente. Sin cuenta de servicio, sin Google
    Cloud, sin secrets. Es el camino por defecto.

    Devuelve None si no esta compartido asi, para que se intente con credencial.
    """
    import requests
    url = f"https://docs.google.com/spreadsheets/d/{file_id}/export?format=xlsx"
    try:
        r = requests.get(url, timeout=180, allow_redirects=True)
    except requests.RequestException as e:
        print(f"  [aviso] no se pudo bajar el Sheet publico: {e}")
        return None

    tipo = r.headers.get("Content-Type", "")
    if r.status_code == 200 and ("spreadsheet" in tipo or "octet-stream" in tipo
                                 or r.content[:2] == b"PK"):
        destino = Path(destino)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(r.content)
        print(f"  Calendario de Eli descargado sin credenciales "
              f"({len(r.content)/1e6:.1f} MB) -> {destino}")
        return destino

    print(f"  [aviso] el Sheet no es accesible por enlace (HTTP {r.status_code}, {tipo}).")
    return None


def descargar_sheet(file_id: str = ID_SHEET_ELI,
                    destino: Path = Path("calendario_eli.xlsx")) -> Path:
    """
    Descarga el fichero de Eli a disco.

    1) Se intenta por enlace publico: cero credenciales.
    2) Si no, con cuenta de servicio (GOOGLE_SERVICE_ACCOUNT_JSON).
    """
    ruta = descargar_publico(file_id, destino)
    if ruta:
        return ruta
    print("  Reintentando con cuenta de servicio...")
    import requests
    from google.auth.transport.requests import Request

    cred = _credencial()
    cred.refresh(Request())
    cab = {"Authorization": f"Bearer {cred.token}"}

    meta = requests.get(
        f"https://www.googleapis.com/drive/v3/files/{file_id}",
        headers=cab, params={"fields": "name,mimeType,modifiedTime",
                             "supportsAllDrives": "true"}, timeout=60)
    if meta.status_code == 404:
        raise SystemExit(
            f"Drive devuelve 404 para {file_id}.\n"
            f"Comparte el fichero con el email de la cuenta de servicio "
            f"(client_email del JSON), con permiso de lectura.")
    meta.raise_for_status()
    m = meta.json()
    print(f"  Drive: {m['name']}  ({m['mimeType']})  modificado {m.get('modifiedTime')}")

    if m["mimeType"] == "application/vnd.google-apps.spreadsheet":
        url = f"https://www.googleapis.com/drive/v3/files/{file_id}/export"
        params = {"mimeType": XLSX}
    else:
        url = f"https://www.googleapis.com/drive/v3/files/{file_id}"
        params = {"alt": "media", "supportsAllDrives": "true"}

    r = requests.get(url, headers=cab, params=params, timeout=180)
    r.raise_for_status()
    destino = Path(destino)
    destino.write_bytes(r.content)
    print(f"  Descargado en {destino}  ({len(r.content)/1e6:.1f} MB)")
    return destino


def calendario_desde_drive(file_id: str = ID_SHEET_ELI, hoja: str = "ELISABET"):
    """Descarga y parsea en un paso. Devuelve el DataFrame largo del calendario."""
    from fuentes import calendario_cobros
    ruta = descargar_sheet(file_id, Path("/tmp/calendario_eli.xlsx"))
    return calendario_cobros(ruta, hoja)


if __name__ == "__main__":
    # Prueba: python google_sheets.py
    print("=" * 74)
    print(" LEASEIR - Prueba de acceso al calendario de Eli")
    print("=" * 74)
    cal = calendario_desde_drive()
    print(f"\n  {len(cal)} cuotas cargadas, {cal['factura'].nunique()} facturas")
    print(f"  desde {cal['mes'].min()} hasta {cal['mes'].max()}")
    print(f"  importe total del calendario: {cal['importe'].sum():,.0f} EUR")
    print("\n  OK: la cuenta de servicio lee el fichero de Eli.")
