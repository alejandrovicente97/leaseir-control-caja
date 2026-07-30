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
    # /credit-notes confirmado en la referencia: "Listado de facturas
    # rectificativas (abonos): notas de credito", scope sales:invoices.read
    "abonos_venta":    (["credit-notes"], False),
    "recibos_venta":   (["sales-receipts", "salesreceipts", "receipts"], False),
    "facturas_compra": (["purchases"], True),
    # No se pide abonos_compra: la v2 NO publica un listado de reembolsos de
    # compra (en la referencia solo hay "Crear una compra rectificativa" y un
    # webhook). Las rectificativas de compra vienen dentro de /purchases con
    # importe negativo, que es justo lo que hace que algun proveedor salga con
    # pendiente positivo. Probar seis rutas inexistentes solo generaba seis 404
    # y un aviso de "bloque vacio" que parecia un fallo y no lo era.
    "contactos":       (["contacts"], False),
    "pagos":           (["payments"], False),
    # Plan contable con debe, haber y saldo por cuenta. Es lo que permite
    # cuadrar el pendiente de cobro contra contabilidad: el saldo de las 430*
    # tiene que ser lo exigible hoy mas lo aplazado segun el calendario.
    "plan_contable":   (["accounting-accounts"], False),
    # Libro diario. Dos motivos por los que volvia vacio, y ninguno era que no
    # existiera: la ruta buena es /ledger-entries (no accounting/entries ni
    # dailyledger, que me invente), y start_date y end_date son OBLIGATORIOS.
    # Sin ellos responde 400 y el bloque se quedaba a cero sin decir por que.
    # Es la fuente mas completa de cobros y pagos: cada apunte lleva su cuenta
    # del plan contable, asi que un movimiento de banco deja de ser un texto
    # ("EMISION REMESA SEPA SDD 0049") y pasa a tener contrapartida.
    "libro_diario":    (["ledger-entries"], False),
}

# Parametros propios de algun recurso, aparte de la ventana general.
PARAMS_V2 = {
    "libro_diario": lambda desde, hasta: {"start_date": str(desde),
                                          "end_date": str(hasta)},
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
# treasury/accounts confirmado en la referencia y en el run #9 (36 cuentas).
# Va primero para no gastar cuatro 404 antes de acertar.
TESORERIA_V2 = ["treasury/accounts", "bank-accounts", "treasuries", "banks"]
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
        extra = PARAMS_V2.get(clave) if v == "v2" else None
        p = dict(ventana)
        if extra:
            p.update(extra(desde, hasta))
        d[clave] = cli.listar(clave, candidatos, **p)
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
            # Los movimientos cuelgan de la misma coleccion que ha respondido
            # para las cuentas: si las cuentas salieron por bank-accounts, los
            # movimientos estan en bank-accounts/{id}/..., no en treasuries/{id}.
            # "Listado de movimientos de una cuenta bancaria" =
            #   /treasury/accounts/{id}/bank-movements   (confirmado, 10.269 movs)
            # cash-movements es la otra mitad: los movimientos de caja.
            raiz = cli.rutas.get("cuentas_tesoreria", "treasury/accounts")
            cands = [f"{raiz}/{cid}/bank-movements",
                     f"{raiz}/{cid}/movements",
                     f"treasury/accounts/{cid}/bank-movements"]
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
    ap.add_argument("--diagnostico", default=None,
                    help="ruta donde dejar el esquema y los conteos (sin datos)")
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
        "truncados": cli.truncados,
    }

    # Diagnostico separado y pequeno: solo nombres de campo, rutas y conteos,
    # cero datos de negocio. Se versiona en el repo para no tener que leer el
    # log de Actions, que se pagina y esconde justo las lineas que importan.
    diag = Path(args.diagnostico) if args.diagnostico else None
    if diag:
        diag.parent.mkdir(parents=True, exist_ok=True)
        with open(diag, "w", encoding="utf-8") as f:
            json.dump(datos["_meta"], f, ensure_ascii=False, indent=1, default=str)
        print(f"  Diagnostico en {diag}")

    destino = Path(args.destino) if args.destino else DESTINO_DEFECTO
    destino.mkdir(parents=True, exist_ok=True)
    salida = destino / "holded.json"
    with open(salida, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=1, default=str)

    print("\n" + "-" * 80)
    for k, val in conteos.items():
        ruta = cli.rutas.get(k, "")
        print(f"  {k:26s} {val:>8,}   {ruta}")
    print("-" * 80)

    # Los nombres de campo reales, en el log y no solo en el json: sin esto hay
    # que adivinar como se llama cada importe y una equivocacion no se ve, se
    # convierte en un numero creible y equivocado.
    print("\n  CAMPOS REALES DE CADA BLOQUE")
    for k, campos in datos["_meta"]["campos"].items():
        print(f"  {k}:\n      {', '.join(campos)}")
    print("-" * 80)
    for a in datos["_meta"]["avisos"]:
        print(f"  [aviso] {a}")
    print(f"  Guardado en {salida}  ({salida.stat().st_size / 1e6:.1f} MB)")

    if not (datos.get("facturas_venta") or datos.get("facturas_compra")):
        print("\n  [ERROR] Ni una factura de venta ni de compra.")
        sys.exit(1)


if __name__ == "__main__":
    main()
