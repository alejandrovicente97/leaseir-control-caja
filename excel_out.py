# -*- coding: utf-8 -*-
"""
============================================================================
 LEASEIR - El Excel de Alejandro, generado en cada actualizacion
============================================================================
Alejandro trabaja en Excel y lo dijo sin rodeos: "serias capaz de que el
unlevered y todo lo que yo hago me lo dieras en excel tal y como lo tengo yo,
actualizado cada vez que recargue". Esto genera ese fichero con la estructura
de sus hojas de trabajo:

  - "Mes en Curso"  la hoja Forecast Caja - Mes en Curso: cada linea con
                    ejecutado, pendiente y proyectado; UNLEVERED arriba,
                    deuda debajo, LEVERED al final cuadrado contra bancos.
  - "Bottom Up"     banco a banco: saldo al empezar, variacion, saldo hoy,
                    y el puente completo hasta el unlevered.
  - "Cobros"        factura a factura cruzada con la proyeccion de Eli:
                    total, deberia cobrado, cobrado, vencido, sin vencer,
                    y la columna editable de "importe previsto".
  - "Pagos"         factura a factura con vencimiento y estado.
  - "Forecast"      los meses del horizonte, linea a linea.

No es una copia byte a byte de su libro -su fichero tiene 50 hojas de
trabajo semanal que son suyas-, es la estructura de sus hojas maestras con
los datos vivos. El fichero se descarga desde el propio panel: va embebido
en la pagina, asi que cada recarga trae el Excel de esa actualizacion.
============================================================================
"""
from __future__ import annotations

from datetime import date

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

AZUL = "1F4D5C"
GRIS = "F1F4F5"
ROJO = "D03B3B"
FMT = "#,##0"

f_cab = Font(bold=True, color="FFFFFF")
f_neg = Font(bold=True)
f_rojo = Font(color=ROJO)
r_cab = PatternFill("solid", fgColor=AZUL)
r_sub = PatternFill("solid", fgColor=GRIS)
borde = Border(bottom=Side(style="thin", color="DDE3E9"))


def _cabecera(ws, fila, textos):
    for j, t in enumerate(textos, start=1):
        c = ws.cell(fila, j, t)
        c.font = f_cab
        c.fill = r_cab
        c.alignment = Alignment(horizontal="right" if j > 1 else "left")
    return fila + 1


def _num(ws, fila, col, v, negrita=False, rojo=False):
    c = ws.cell(fila, col, round(float(v)) if v is not None else None)
    c.number_format = FMT
    if negrita:
        c.font = f_neg
    if rojo and v is not None and v < 0:
        c.font = f_rojo
    return c


def _fila(ws, fila, concepto, valores, negrita=False, sub=False):
    c = ws.cell(fila, 1, concepto)
    if negrita:
        c.font = f_neg
    if sub:
        for j in range(1, len(valores) + 2):
            ws.cell(fila, j).fill = r_sub
        c.font = f_neg
    for j, v in enumerate(valores, start=2):
        _num(ws, fila, j, v, negrita=negrita or sub, rojo=True)
        if sub:
            ws.cell(fila, j).fill = r_sub
    return fila + 1


def _anchos(ws, anchos):
    for j, a in enumerate(anchos, start=1):
        ws.column_dimensions[get_column_letter(j)].width = a


def generar(ruta, fc, cuadre, meta) -> None:
    wb = Workbook()

    # ---- Mes en Curso -----------------------------------------------------
    ws = wb.active
    ws.title = "Mes en Curso"
    mec = meta.get("mes_en_curso")
    if mec:
        t = mec["tot"]
        ws.cell(1, 1, f"Forecast Caja - {mec['etiqueta']}").font = Font(bold=True, size=14)
        ws.cell(2, 1, f"Generado el {date.today():%d/%m/%Y} desde Holded. "
                      f"Ejecutado = libro diario, cada euro en una sola linea.")
        f = 4
        f = _cabecera(ws, f, ["Concepto", "Ejecutado", "Pendiente", "Mes proyectado"])
        f = _fila(ws, f, "CASH IN", [t["in_ej"], t["in_pd"], t["in_tot"]], sub=True)
        for x in mec["cash_in"]:
            if abs(x["ejecutado"]) > 0.005 or abs(x["pendiente"]) > 0.005:
                f = _fila(ws, f, "    " + x["concepto"],
                          [x["ejecutado"], x["pendiente"], x["total"]])
        f = _fila(ws, f, "CASH OUT (sin deuda)",
                  [t["out_ej"], t["out_pd"], t["out_tot"]], sub=True)
        for x in mec["cash_out"]:
            if abs(x["ejecutado"]) > 0.005 or abs(x["pendiente"]) > 0.005:
                f = _fila(ws, f, "    " + x["concepto"],
                          [x["ejecutado"], x["pendiente"], x["total"]])
        f = _fila(ws, f, "UNLEVERED FCF",
                  [t["unlev_ej"], t["unlev_pd"], t["unlev_tot"]], negrita=True)
        fd = mec["deuda"]
        f = _fila(ws, f, "    " + fd["concepto"], [fd["ejecutado"], 0, fd["total"]])
        f = _fila(ws, f, "LEVERED FCF (= variacion de caja)",
                  [t["lev_ej"], t["lev_pd"], t["lev_tot"]], negrita=True)
        f += 1
        cn = mec["concil"]
        f = _cabecera(ws, f, ["El levered, contra los bancos", "Importe"])
        f = _fila(ws, f, "LEVERED ejecutado = variacion contable de bancos",
                  [cn["contable"]])
        f = _fila(ws, f, "Pendiente de conciliar del mes (con signo)",
                  [cn["pendiente"]])
        f = _fila(ws, f, "Descuadre restante", [cn["descuadre"]])
        f = _fila(ws, f, "= Variacion de saldos bancarios (dia 1 -> hoy)",
                  [cn["saldos"]], negrita=True)
        f += 1
        f = _fila(ws, f, "Saldo hoy", [mec["saldo_hoy"]], negrita=True)
        f = _fila(ws, f, "+ pendiente del mes", [t["lev_pd"]])
        f = _fila(ws, f, "= Saldo proyectado a cierre", [mec["saldo_cierre"]],
                  negrita=True)
        _anchos(ws, [52, 16, 16, 16])

    # ---- Bottom Up --------------------------------------------------------
    ws = wb.create_sheet("Bottom Up")
    eje = fc.get("ejecutado") or {}
    bk = eje.get("banco") or {}
    ws.cell(1, 1, "Bottom Up - banco a banco").font = Font(bold=True, size=14)
    f = 3
    f = _cabecera(ws, f, ["Cuenta", "Al empezar el mes", "Hoy", "Variacion", "Movs"])
    pc = bk.get("por_cuenta") or []
    for x in pc:
        f = _fila(ws, f, x["cuenta"], [x["inicio"], x["hoy"], x["variacion"], x["n"]])
        ws.cell(f - 1, 5).number_format = "0"
    f = _fila(ws, f, "TOTAL",
              [sum(x["inicio"] for x in pc), sum(x["hoy"] for x in pc),
               sum(x["variacion"] for x in pc), None], sub=True)
    f += 1
    f = _cabecera(ws, f, ["Del banco al unlevered", "Importe"])
    f = _fila(ws, f, "Saldo del banco al empezar el mes", [bk.get("saldo_inicio", 0)])
    f = _fila(ws, f, "Saldo del banco hoy", [bk.get("saldo_hoy", 0)])
    f = _fila(ws, f, "Variacion del saldo bancario",
              [bk.get("variacion_bancos", 0)], negrita=True)
    f = _fila(ws, f, "Gasto en tarjeta del mes (no llega al banco hasta el mes que viene)",
              [bk.get("gasto_tarjeta_mes", 0)])
    f = _fila(ws, f, "LEVERED FCF", [bk.get("levered", 0)], negrita=True)
    for x in (eje.get("detalle_deuda") or []):
        f = _fila(ws, f, f"    {x['cuenta']} {x['nombre'] or 'deuda'}", [x["importe"]])
    f = _fila(ws, f, "Pagos de deuda del mes", [bk.get("deuda", 0)])
    f = _fila(ws, f, "UNLEVERED FCF", [bk.get("unlevered", 0)], negrita=True)
    _anchos(ws, [52, 18, 16, 14, 8])

    # ---- Cobros -----------------------------------------------------------
    ws = wb.create_sheet("Cobros")
    cbb = meta.get("cobrabilidad")
    dfc = cbb[0] if cbb else None
    f = _cabecera(ws, 1, ["Cliente", "Factura", "Vencimiento", "Total factura",
                          "Deberia cobrado (Eli)", "Cobrado", "Vencido",
                          "Sin vencer", "¿Se cobra?", "Importe previsto"])
    dc = fc.get("detalle_cobros")
    if dc is not None and not dc.empty:
        e = dc.copy()
        e["vencido_i"] = (e["teorico_hoy"] - e["liquidado"]).clip(lower=0)
        e["sin_vencer"] = (e["total"] - e[["teorico_hoy", "liquidado"]].max(axis=1)).clip(lower=0)
        entra = {}
        if dfc is not None and not dfc.empty:
            entra = dict(zip(dfc["num"], dfc["entra"]))
        act = e[(e["vencido_i"] > 0.01) | (e["sin_vencer"] > 0.01)
                | (e["liquidado"].abs() > 0.01)]
        for _, r in act.sort_values(["cliente", "vencido_i"],
                                    ascending=[True, False]).iterrows():
            ws.cell(f, 1, r["cliente"])
            ws.cell(f, 2, str(r["num"]))
            ws.cell(f, 3, str(r.get("vencimiento") or ""))
            _num(ws, f, 4, r["total"])
            _num(ws, f, 5, r["teorico_hoy"])
            _num(ws, f, 6, r["liquidado"])
            _num(ws, f, 7, r["vencido_i"], rojo=True)
            if r["vencido_i"] > 0.01:
                ws.cell(f, 7).font = f_rojo
            _num(ws, f, 8, r["sin_vencer"])
            en = entra.get(r["num"])
            ws.cell(f, 9, "" if en is None else ("SI" if en else "NO"))
            pend = r["teorico_hoy"] - r["liquidado"]
            _num(ws, f, 10, max(0.0, pend) if en else 0.0)
            f += 1
    _anchos(ws, [36, 16, 13, 14, 18, 13, 13, 13, 11, 15])
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:J{max(2, f - 1)}"

    # ---- Pagos ------------------------------------------------------------
    ws = wb.create_sheet("Pagos")
    f = _cabecera(ws, 1, ["Proveedor", "Factura", "Vencimiento", "Tipologia",
                          "Total", "Pagado", "Pendiente", "Estado"])
    dp = fc.get("detalle_pagos")
    if dp is not None and not dp.empty:
        for _, r in dp[dp["pendiente"] > 0.01].sort_values(
                ["vencido", "vencimiento"], ascending=[False, True]).iterrows():
            ws.cell(f, 1, r["proveedor"])
            ws.cell(f, 2, str(r["num"]))
            ws.cell(f, 3, str(r.get("vencimiento") or ""))
            ws.cell(f, 4, str(r.get("tipologia") or ""))
            _num(ws, f, 5, -r["total"])
            _num(ws, f, 6, -r["liquidado"])
            _num(ws, f, 7, -r["pendiente"], rojo=True)
            ws.cell(f, 8, "VENCIDO" if r["vencido"] else str(r.get("estado") or ""))
            if r["vencido"]:
                ws.cell(f, 8).font = f_rojo
            f += 1
    _anchos(ws, [36, 16, 13, 15, 13, 13, 13, 12])
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:H{max(2, f - 1)}"

    # ---- Forecast ---------------------------------------------------------
    ws = wb.create_sheet("Forecast")
    meses = fc["meses"]
    ets = [fc["lineas"][m]["etiqueta"] for m in meses]
    f = _cabecera(ws, 1, ["Concepto"] + ets)
    CLAVES = [("Cobro clientes", "cobro_clientes"),
              ("Rentings sin factura", "rentings_sin_factura"),
              ("Ventas fusion LML", "ventas_fusion_lml"),
              ("Ventas sin facturar", "ventas_sin_facturar"),
              ("Ajustes", "ajustes_cobros"),
              ("CASH IN", "cash_in"),
              ("Pago proveedores", "pago_proveedores"),
              ("Salarios y SS", "salarios"),
              ("Cuotas S&L", "cuotas_sl"),
              ("Recurrentes", "recurrentes_proyectados"),
              ("Otros fijos", "otros_fijos"),
              ("CASH OUT", "cash_out"),
              ("FCF", "fcf"),
              ("Saldo proyectado", "saldo_proyectado")]
    for nombre, k in CLAVES:
        vals = [fc["lineas"][m].get(k, 0) for m in meses]
        f = _fila(ws, f, nombre, vals,
                  sub=k in ("cash_in", "cash_out"),
                  negrita=k in ("fcf", "saldo_proyectado"))
    _anchos(ws, [26] + [15] * len(meses))

    wb.save(ruta)
