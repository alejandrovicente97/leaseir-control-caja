#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================================
 LEASEIR - Extraccion de Holded
============================================================================
 Trae de Holded todo lo que el forecast de caja necesita:

   ventas    facturas y abonos de venta de los ultimos 4 anos
   compras   facturas y abonos de compra, mismo rango
   caja      cuentas de tesoreria con sus saldos y sus movimientos
   apoyo     contactos y libro diario

 Corre en GitHub Actions cada manana. Tambien vale en local:

     export HOLDED_API_KEY=...
     python holded_extract.py --anos 4
     python holded_extract.py --probar        # solo sondea y sale

 Principio: ningun bloque opcional tumba la extraccion. Si Holded no sirve un
 tipo de documento, se avisa, se deja vacio y se sigue. Solo se falla si no
 hay forma de autenticarse o si no llega ni una factura.
============================================================================
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, date
from pathlib import Path

try:
    import requests  # noqa: F401  (lo usa holded_client)
except ImportError:
    sys.exit("Falta la libreria requests.  Ejecuta:  pip install requests")

from holded_client import (Holded, HoldedError, ts,
                           BASE_INVOICING, BASE_ACCOUNTING)

API_KEY = os.environ.get("HOLDED_API_KEY", "").strip()

DESTINO_DEFECTO = Path(os.environ.get(
    "LEASEIR_DATA_DIR",
    Path.home() / "OneDrive - Leaseir Technologies" / "Leaseir - Finance - Documentos"
    / "General" / "Leaseir - Finance" / "2026" / "19. Control Caja" / "_data_holded"
))

# (clave interna, tipo de documento en Holded, imprescindible)
DOCUMENTOS = [
    ("facturas_venta",  "invoice",        True),
    ("abonos_venta",    "creditnote",     False),
    ("facturas_compra", "purchase",       True),
    ("abonos_compra",   "purchaserefund", False),
    ("recibos_venta",   "salesreceipt",   False),
]


# ---------------------------------------------------------------------------
def extraer(cli: Holded, desde: date, hasta: date) -> dict:
    t0, t1 = ts(desde), ts(hasta)
    d: dict = {}
    avisos: list[str] = []

    print("\n  DOCUMENTOS")
    for clave, tipo, obligatorio in DOCUMENTOS:
        print(f"  > {clave} ({tipo})")
        # Primero con ventana temporal; si Holded la rechaza, sin ella.
        lote = cli.paginar(f"{BASE_INVOICING}/documents/{tipo}",
                           etiqueta=clave, starttmp=t0, endtmp=t1)
        if not lote:
            print(f"    reintento de {clave} sin ventana temporal")
            lote = cli.paginar(f"{BASE_INVOICING}/documents/{tipo}", etiqueta=clave)
        d[clave] = lote or []
        if not d[clave]:
            msg = f"{clave} ({tipo}) ha venido vacio"
            avisos.append(msg)
            if obligatorio:
                print(f"    [ATENCION] {msg} y es imprescindible")

    print("\n  CONTACTOS")
    d["contactos"] = cli.paginar(f"{BASE_INVOICING}/contacts", etiqueta="contactos") or []
    if not d["contactos"]:
        # en algunas cuentas van separados
        for alt in ("customers", "suppliers"):
            extra = cli.paginar(f"{BASE_INVOICING}/{alt}", etiqueta=alt)
            d["contactos"].extend(extra or [])

    print("\n  TESORERIA")
    cuentas = cli.get(f"{BASE_INVOICING}/treasury")
    if isinstance(cuentas, dict):
        cuentas = cuentas.get("data") or cuentas.get("items") or []
    d["cuentas_tesoreria"] = cuentas or []
    print(f"    {len(d['cuentas_tesoreria'])} cuentas")
    for c in d["cuentas_tesoreria"]:
        if isinstance(c, dict):
            print(f"      - {c.get('name')}  saldo {c.get('balance')}")
    if not d["cuentas_tesoreria"]:
        avisos.append("no se han podido leer las cuentas de tesoreria: "
                      "la posicion bancaria y el cuadre quedaran sin datos")

    movs = []
    for c in d["cuentas_tesoreria"]:
        if not isinstance(c, dict):
            continue
        cid = c.get("id") or c.get("_id")
        if not cid:
            continue
        nombre = c.get("name", cid)
        lote = None
        for patron in (f"{BASE_INVOICING}/treasury/{cid}/movements",
                       f"{BASE_INVOICING}/treasury/{cid}/transactions",
                       f"{BASE_INVOICING}/treasury/movements"):
            lote = cli.paginar(patron, etiqueta=f"movs {nombre}",
                               starttmp=t0, endtmp=t1)
            if lote:
                break
        for m in (lote or []):
            if isinstance(m, dict):
                m["_cuenta_id"] = cid
                m["_cuenta_nombre"] = nombre
        movs.extend(lote or [])
    d["movimientos_tesoreria"] = movs
    if not movs:
        avisos.append("sin movimientos de tesoreria: el cuadre contra banco "
                      "quedara como 'pendiente'")

    print("\n  CONTABILIDAD")
    d["libro_diario"] = cli.paginar(f"{BASE_ACCOUNTING}/dailyledger",
                                    etiqueta="libro diario",
                                    starttmp=t0, endtmp=t1) or []

    d["_avisos"] = avisos
    return d


# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description="Extraccion de Holded para el forecast de caja")
    ap.add_argument("--anos", type=int, default=4,
                    help="anos de historico de ventas y compras (por defecto 4)")
    ap.add_argument("--desde", default=None,
                    help="fecha inicio YYYY-MM-DD (manda sobre --anos)")
    ap.add_argument("--hasta", default=None, help="fecha fin YYYY-MM-DD")
    ap.add_argument("--destino", default=None, help="carpeta de salida")
    ap.add_argument("--probar", action="store_true",
                    help="solo sondea la API y sale, sin descargar nada")
    args = ap.parse_args()

    hoy = date.today()
    if args.desde:
        desde = datetime.strptime(args.desde, "%Y-%m-%d").date()
    else:
        desde = date(hoy.year - args.anos, 1, 1)
    hasta = (datetime.strptime(args.hasta, "%Y-%m-%d").date() if args.hasta
             else date(hoy.year + 2, 12, 31))

    print("=" * 80)
    print(" LEASEIR - Extraccion de Holded")
    print(f" Periodo : {desde}  ->  {hasta}")
    print("=" * 80)

    try:
        cli = Holded(API_KEY)
        cli.autenticar()
    except HoldedError as e:
        print("\n" + "!" * 80)
        print(str(e))
        print("!" * 80)
        sys.exit(1)

    if args.probar:
        print("\n  Sondeo correcto. No se descarga nada (--probar).")
        return

    datos = extraer(cli, desde, hasta)

    conteos = {k: len(v) for k, v in datos.items() if isinstance(v, list)}
    datos["_meta"] = {
        "extraido_en": datetime.now().isoformat(timespec="seconds"),
        "desde": str(desde), "hasta": str(hasta),
        "modo_auth": cli.modo, "conteos": conteos,
        "avisos": datos.get("_avisos", []),
    }

    destino = Path(args.destino) if args.destino else DESTINO_DEFECTO
    destino.mkdir(parents=True, exist_ok=True)
    salida = destino / "holded.json"
    with open(salida, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=1, default=str)

    print("\n" + "-" * 80)
    for k, v in conteos.items():
        print(f"  {k:26s} {v:>8,}")
    print("-" * 80)
    for a in datos["_meta"]["avisos"]:
        print(f"  [aviso] {a}")
    print(f"  Guardado en {salida}  ({salida.stat().st_size / 1e6:.1f} MB)")

    ventas = len(datos.get("facturas_venta") or [])
    compras = len(datos.get("facturas_compra") or [])
    if ventas == 0 and compras == 0:
        print("\n  [ERROR] Ni una factura de venta ni de compra. Algo va mal.")
        sys.exit(1)


if __name__ == "__main__":
    main()
