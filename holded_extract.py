#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================================
 LEASEIR - Extraccion de Holded
============================================================================
 Trae lo que el forecast de caja necesita:

   ventas    facturas, abonos y tickets de los ultimos 4 anos
   compras   facturas de compra y reembolsos, mismo rango
   caja      cuentas bancarias con sus saldos y sus movimientos
   apoyo     contactos, pagos y libro diario

 Funciona contra la API v2 de Holded (tokens pat_, Bearer) y contra la v1
 obsoleta, segun lo que sea la clave. Ver holded_client.py.

     export HOLDED_API_KEY=...
     python holded_extract.py --anos 4
     python holded_extract.py --probar      # solo detecta version y sale

 Ningun bloque opcional tumba la extraccion: si un recurso no responde se
 avisa, se deja vacio y se sigue. Solo se falla si no hay forma de
 autenticarse o si no llega ni una factura.
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
    import requests  # noqa: F401
except ImportError:
    sys.exit("Falta la libreria requests.  Ejecuta:  pip install requests")

from holded_client import Holded, HoldedError, ts, BASE_V1, BASE_V1_CONTA

API_KEY = os.environ.get("HOLDED_API_KEY", "").strip()

DESTINO_DEFECTO = Path(os.environ.get(
    "LEASEIR_DATA_DIR",
    Path.home() / "OneDrive - Leaseir Technologies" / "Leaseir - Finance - Documentos"
    / "General" / "Leaseir - Finance" / "2026" / "19. Control Caja" / "_data_holded"
))

# Rutas candidatas por recurso. La referencia de Holded lista los endpoints por
# titulo y no por path, asi que se prueban varios nombres razonables en vez de
# apostar por uno. El cliente recuerda el que responde.
RECURSOS_V2 = {
    "facturas_venta":  (["invoices", "sales/invoices"], True),
    "abonos_venta":    (["credit-notes", "sales/credit-notes", "sales-refunds",
                         "salesrefunds", "rectificative-invoices"], False),
    "recibos_venta":   (["sales-receipts", "salesreceipts", "receipts"], False),
    "facturas_compra": (["purchases", "purchase-invoices", "expenses"], True),
    "abonos_compra":   (["purchases-refunds", "purchase-refunds", "refunds",
                         "purchase-credit-notes", "purchases/credit-notes",
                         "expenses-refunds"], False),
    "contactos":       (["contacts"], False),
    "pagos":           (["payments"], False),
    "libro_diario":    (["accounting/entries", "accounting/journal-entries",
                         "journal-entries", "dailyledger"], False),
}
RECURSOS_V1 = {
    "facturas_venta":  ([f"{BASE_V1}/documents/invoice"], True),
    "abonos_venta":    ([f"{BASE_V1}/documents/creditnote"], False),
    "recibos_venta":   ([f"{BASE_V1}/documents/salesreceipt"], False),
    "facturas_compra": ([f"{BASE_V1}/documents/purchase"], True),
    "abonos_compra":   ([f"{BASE_V1}/documents/purchaserefund"], False),
    "contactos":       ([f"{BASE_V1}/contacts"], False),
    "pagos":           ([f"{BASE_V1}/payments"], False),
    "libro_diario":    ([f"{BASE_V1_CONTA}/dailyledger"], False),
}
# La referencia de Holded titula esto "Listado de cuentas bancarias", sin dar
# el path. Se prueban los nombres razonables y el cliente recuerda el que va.
TESORERIA_V2 = ["bank-accounts", "treasuries", "treasury", "banks",
                "bank_accounts", "treasury/accounts", "accounts"]
TESORERIA_V1 = [f"{BASE_V1}/treasury"]


def extraer(cli: Holded, desde: date, hasta: date) -> dict:
    v = cli.autenticar()
    recursos = RECURSOS_V2 if v == "v2" else RECURSOS_V1
    tesoreria = TESORERIA_V2 if v == "v2" else TESORERIA_V1
    # la v1 filtra por timestamp; la v2 no documenta ese parametro, se trae todo
    ventana = {} if v == "v2" else {"starttmp": ts(desde), "endtmp": ts(hasta)}

    d, avisos = {}, []

    print(f"\n  DOCUMENTOS  (API {v})")
    for clave, (candidatos, obligatorio) in recursos.items():
        print(f"  > {clave}")
        d[clave] = cli.listar(clave, candidatos, **ventana)
        if not d[clave]:
            avisos.append(f"{clave} ha venido vacio")
            if obligatorio:
                print(f"    [ATENCION] {clave} esta vacio y es imprescindible")

    print("\n  TESORERIA")
    cuentas = cli.listar("cuentas_tesoreria", tesoreria)
    d["cuentas_tesoreria"] = cuentas
    for c in cuentas:
        if isinstance(c, dict):
            print(f"      - {c.get('name')}  saldo {c.get('balance')}")
    if not cuentas:
        avisos.append("sin cuentas bancarias: la posicion y el cuadre se quedan sin base")

    movs = []
    for c in cuentas:
        if not isinstance(c, dict):
            continue
        cid = c.get("id") or c.get("_id")
        if not cid:
            continue
        nombre = c.get("name", cid)
        if v == "v2":
            cands = [f"treasuries/{cid}/movements",
                     f"treasuries/{cid}/bank-movements",
                     f"treasuries/{cid}/cash-movements"]
        else:
            cands = [f"{BASE_V1}/treasury/{cid}/movements"]
        lote = cli.listar(f"movs::{cid}", cands, **ventana)
        for m in lote:
            if isinstance(m, dict):
                m["_cuenta_id"] = cid
                m["_cuenta_nombre"] = nombre
        movs.extend(lote)
    d["movimientos_tesoreria"] = movs
    if not movs:
        avisos.append("sin movimientos bancarios: el cuadre contra banco "
                      "quedara como pendiente")

    d["_avisos"] = avisos
    return d


def main() -> None:
    ap = argparse.ArgumentParser(description="Extraccion de Holded")
    ap.add_argument("--anos", type=int, default=4)
    ap.add_argument("--desde", default=None)
    ap.add_argument("--hasta", default=None)
    ap.add_argument("--destino", default=None)
    ap.add_argument("--probar", action="store_true")
    args = ap.parse_args()

    hoy = date.today()
    desde = (datetime.strptime(args.desde, "%Y-%m-%d").date() if args.desde
             else date(hoy.year - args.anos, 1, 1))
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
        print("\n  Deteccion correcta. No se descarga nada (--probar).")
        return

    datos = extraer(cli, desde, hasta)
    conteos = {k: len(v) for k, v in datos.items() if isinstance(v, list)}
    datos["_meta"] = {
        "extraido_en": datetime.now().isoformat(timespec="seconds"),
        "desde": str(desde), "hasta": str(hasta),
        "api": cli.version, "rutas": cli.rutas,
        # nombres de campo reales del primer registro de cada bloque: sirve para
        # no tener que adivinar el esquema en la proxima vuelta
        "campos": {k: sorted(v[0].keys())
                   for k, v in datos.items()
                   if isinstance(v, list) and v and isinstance(v[0], dict)},
        "conteos": conteos, "avisos": datos.get("_avisos", []),
    }

    destino = Path(args.destino) if args.destino else DESTINO_DEFECTO
    destino.mkdir(parents=True, exist_ok=True)
    salida = destino / "holded.json"
    with open(salida, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=1, default=str)

    print("\n" + "-" * 80)
    for k, val in conteos.items():
        print(f"  {k:26s} {val:>8,}")
    print("-" * 80)
    for a in datos["_meta"]["avisos"]:
        print(f"  [aviso] {a}")
    print(f"  Guardado en {salida}  ({salida.stat().st_size / 1e6:.1f} MB)")

    if not (datos.get("facturas_venta") or datos.get("facturas_compra")):
        print("\n  [ERROR] Ni una factura de venta ni de compra.")
        sys.exit(1)


if __name__ == "__main__":
    main()
