#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================================
 LEASEIR - Extractor de Holded
============================================================================
 ESTE SCRIPT SE EJECUTA EN TU PC (necesita salida a internet).
 Descarga de Holded todo lo que hace falta para el forecast de caja y lo
 deja en JSON dentro de la carpeta de OneDrive, donde el motor lo recoge.

 Uso:
     python holded_extract.py
     python holded_extract.py --desde 2024-01-01

 Requisitos:  pip install requests
============================================================================
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, date, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("Falta la libreria requests.  Ejecuta:  pip install requests")

# ---------------------------------------------------------------------------
# CONFIGURACION
# ---------------------------------------------------------------------------
API_KEY = os.environ.get("HOLDED_API_KEY", "").strip()

# Carpeta destino: la de OneDrive que ya usas para Control Caja
DESTINO = Path(os.environ.get(
    "LEASEIR_DATA_DIR",
    Path.home() / "OneDrive - Leaseir Technologies" / "Leaseir - Finance - Documentos"
    / "General" / "Leaseir - Finance" / "2026" / "19. Control Caja" / "_data_holded"
))

BASE_INVOICING = "https://api.holded.com/api/invoicing/v1"
BASE_ACCOUNTING = "https://api.holded.com/api/accounting/v1"
TIMEOUT = 60
PAUSA = 0.35          # segundos entre llamadas, para no saturar la API


# ---------------------------------------------------------------------------
# CLIENTE
# ---------------------------------------------------------------------------
class Holded:
    """Cliente minimo de la API de Holded, tolerante a las dos formas de auth."""

    def __init__(self, api_key: str):
        if not api_key:
            raise SystemExit(
                "No hay API key.\n"
                "  Windows :  set HOLDED_API_KEY=tu_key\n"
                "  Mac/Linux: export HOLDED_API_KEY=tu_key"
            )
        self.key = api_key
        self.s = requests.Session()
        self.auth_mode = None

    # -- autenticacion -------------------------------------------------------
    # Holded ha cambiado de formato de token con el tiempo y no todas las
    # variantes usan la misma cabecera. Un 400 no significa token invalido:
    # significa peticion mal formada, normalmente por mandar Content-Type en
    # un GET o un parametro que ese endpoint no acepta. Se prueban todas y se
    # deja constancia de lo que responde Holded en cada caso.
    MODOS = [
        ("key",            {"key": "{k}"},                        True),
        ("key-sin-ct",     {"key": "{k}"},                        False),
        ("bearer",         {"Authorization": "Bearer {k}"},       True),
        ("bearer-sin-ct",  {"Authorization": "Bearer {k}"},       False),
        ("x-api-key",      {"X-API-KEY": "{k}"},                  False),
        ("x-auth-token",   {"X-AUTH-TOKEN": "{k}"},               False),
    ]

    def _headers(self, mode: str) -> dict:
        for nombre, plantilla, con_ct in self.MODOS:
            if nombre == mode:
                h = {"Accept": "application/json"}
                if con_ct:
                    h["Content-Type"] = "application/json"
                for cab, val in plantilla.items():
                    h[cab] = val.format(k=self.key)
                return h
        return {"Accept": "application/json", "key": self.key}

    def _detect_auth(self) -> str:
        if self.auth_mode:
            return self.auth_mode

        print("  Probando formas de autenticacion contra Holded...")
        ultimo = None
        for nombre, _, _ in self.MODOS:
            for params in ({}, {"page": 1}):
                try:
                    r = self.s.get(f"{BASE_INVOICING}/contacts",
                                   headers=self._headers(nombre),
                                   params=params, timeout=TIMEOUT)
                except requests.RequestException as e:
                    raise SystemExit(f"No hay conexion con api.holded.com: {e}")
                etiqueta = f"{nombre}{' +page' if params else ''}"
                print(f"    {etiqueta:20s} HTTP {r.status_code}  {r.text[:120].strip()}")
                ultimo = r
                if r.status_code == 200:
                    self.auth_mode = nombre
                    self.params_extra = params
                    print(f"  [ok] Funciona con '{nombre}'")
                    return nombre
                time.sleep(0.2)

        raise SystemExit(
            f"Ninguna forma de autenticacion ha funcionado (ultimo HTTP {ultimo.status_code}).\n"
            f"Respuesta de Holded: {ultimo.text[:400]}\n\n"
            "Arriba esta el detalle de cada intento. Un 400 apunta a formato de\n"
            "peticion; un 401 o 403, a permisos del token en\n"
            "Holded > Ajustes > Desarrolladores > Credenciales."
        )

    # -- peticiones ----------------------------------------------------------
    def get(self, url: str, **params):
        mode = self._detect_auth()
        for intento in range(4):
            r = self.s.get(url, headers=self._headers(mode), params=params, timeout=TIMEOUT)
            if r.status_code == 200:
                try:
                    return r.json()
                except ValueError:
                    return []
            if r.status_code in (429, 500, 502, 503, 504):
                espera = 2 ** intento
                print(f"    HTTP {r.status_code}, reintento en {espera}s...")
                time.sleep(espera)
                continue
            print(f"    [aviso] HTTP {r.status_code} en {url} -> {r.text[:180]}")
            return []
        return []

    def paginar(self, url: str, **params) -> list:
        """Recorre todas las paginas. Holded devuelve lista vacia al terminar."""
        salida, page = [], 1
        while True:
            lote = self.get(url, page=page, **params)
            if isinstance(lote, dict):
                lote = lote.get("data") or lote.get("items") or []
            if not lote:
                break
            salida.extend(lote)
            print(f"    pagina {page:>3}  (+{len(lote):>4})  acumulado {len(salida)}")
            if len(lote) < 100:
                break
            page += 1
            time.sleep(PAUSA)
            if page > 400:
                print("    [aviso] corte de seguridad a 400 paginas")
                break
        return salida


# ---------------------------------------------------------------------------
# EXTRACCIONES
# ---------------------------------------------------------------------------
def ts(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())


def extraer(cli: Holded, desde: date, hasta: date) -> dict:
    t0, t1 = ts(desde), ts(hasta)
    datos: dict = {}

    bloques = [
        ("facturas_venta",   f"{BASE_INVOICING}/documents/invoice",       dict(starttmp=t0, endtmp=t1)),
        ("abonos_venta",     f"{BASE_INVOICING}/documents/creditnote",    dict(starttmp=t0, endtmp=t1)),
        ("facturas_compra",  f"{BASE_INVOICING}/documents/purchase",      dict(starttmp=t0, endtmp=t1)),
        ("abonos_compra",    f"{BASE_INVOICING}/documents/purchaserefund", dict(starttmp=t0, endtmp=t1)),
        ("contactos",        f"{BASE_INVOICING}/contacts",                {}),
    ]
    for nombre, url, params in bloques:
        print(f"  > {nombre}")
        datos[nombre] = cli.paginar(url, **params)
        time.sleep(PAUSA)

    # Tesoreria: cuentas y movimientos -------------------------------------
    print("  > cuentas de tesoreria")
    cuentas = cli.get(f"{BASE_INVOICING}/treasury")
    if isinstance(cuentas, dict):
        cuentas = cuentas.get("data") or []
    datos["cuentas_tesoreria"] = cuentas or []
    print(f"    {len(datos['cuentas_tesoreria'])} cuentas")

    movs = []
    for c in datos["cuentas_tesoreria"]:
        cid = c.get("id")
        if not cid:
            continue
        print(f"    movimientos de {c.get('name', cid)}")
        lote = cli.paginar(f"{BASE_INVOICING}/treasury/{cid}/movements",
                           starttmp=t0, endtmp=t1)
        for m in lote:
            m["_cuenta_id"] = cid
            m["_cuenta_nombre"] = c.get("name")
        movs.extend(lote)
        time.sleep(PAUSA)
    datos["movimientos_tesoreria"] = movs

    # Libro diario ----------------------------------------------------------
    print("  > libro diario")
    datos["libro_diario"] = cli.paginar(f"{BASE_ACCOUNTING}/dailyledger",
                                        starttmp=t0, endtmp=t1)

    return datos


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def probar() -> None:
    """
    Comprobacion rapida: valida la API key y enseña los nombres reales de los
    campos que devuelve Holded. Si algun nombre no coincide con lo que espera
    fuentes.py, se ve aqui en 10 segundos en vez de en el forecast.
    """
    print("=" * 74)
    print(" LEASEIR - Prueba de conexion con Holded")
    print("=" * 74)
    cli = Holded(API_KEY)
    pruebas = [
        ("Facturas de venta",   f"{BASE_INVOICING}/documents/invoice"),
        ("Facturas de compra",  f"{BASE_INVOICING}/documents/purchase"),
        ("Contactos",           f"{BASE_INVOICING}/contacts"),
        ("Cuentas de tesoreria", f"{BASE_INVOICING}/treasury"),
    ]
    for nombre, url in pruebas:
        r = cli.get(url, page=1)
        if isinstance(r, dict):
            r = r.get("data") or r.get("items") or []
        print(f"\n--- {nombre} ---")
        if not r:
            print("   sin datos o endpoint no disponible")
            continue
        print(f"   {len(r)} registros en la primera pagina")
        print("   campos:", ", ".join(sorted(r[0].keys())))
        ej = {k: v for k, v in list(r[0].items())[:9]}
        print("   ejemplo:", json.dumps(ej, ensure_ascii=False, default=str)[:420])
    print("\n" + "=" * 74)
    print(" Si algun campo no coincide, pega esta salida en el chat y se ajusta.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Extractor de Holded para el forecast de caja")
    ap.add_argument("--desde", default="2024-01-01", help="fecha inicio YYYY-MM-DD")
    ap.add_argument("--hasta", default=None, help="fecha fin YYYY-MM-DD (por defecto +18 meses)")
    ap.add_argument("--destino", default=None, help="carpeta de salida")
    ap.add_argument("--probar", action="store_true",
                    help="solo comprueba la conexion y enseña los campos que devuelve Holded")
    args = ap.parse_args()

    if args.probar:
        probar()
        return

    desde = datetime.strptime(args.desde, "%Y-%m-%d").date()
    if args.hasta:
        hasta = datetime.strptime(args.hasta, "%Y-%m-%d").date()
    else:
        hoy = date.today()
        hasta = date(hoy.year + 2, hoy.month, 1)

    destino = Path(args.destino) if args.destino else DESTINO
    destino.mkdir(parents=True, exist_ok=True)

    print("=" * 74)
    print(" LEASEIR - Extraccion de Holded")
    print(f" Periodo : {desde}  ->  {hasta}")
    print(f" Destino : {destino}")
    print("=" * 74)

    cli = Holded(API_KEY)
    datos = extraer(cli, desde, hasta)

    datos["_meta"] = {
        "extraido_en": datetime.now().isoformat(timespec="seconds"),
        "desde": str(desde),
        "hasta": str(hasta),
        "conteos": {k: len(v) for k, v in datos.items() if isinstance(v, list)},
    }

    salida = destino / "holded.json"
    with open(salida, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=1, default=str)

    # copia con sello de fecha, para tener historico
    sello = destino / f"holded_{date.today():%Y%m%d}.json"
    with open(sello, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=1, default=str)

    print("-" * 74)
    for k, v in datos["_meta"]["conteos"].items():
        print(f"  {k:26s} {v:>7,}")
    print("-" * 74)
    print(f" Guardado en {salida}")
    print(f" Tamano: {salida.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
