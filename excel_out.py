# -*- coding: utf-8 -*-
"""
============================================================================
 LEASEIR - El Excel de Alejandro, con su flujo de trabajo de verdad
============================================================================
No es un volcado de numeros: es SU libro. La hoja maestra "Forecast Caja -
Mes en Curso" calcula con FORMULAS sobre las subpestanas, exactamente como
hace su fichero 20260717 - Forecast CashFlow.xlsx:

    Forecast   =IFERROR(VLOOKUP($D7,Cobros!$A:$B,2,0),0)
    Adicional  =SUMIFS('Clientes (Nuevos)'!$K:$K,'Clientes (Nuevos)'!$B:$B,$D7)
    Ejecutado  =SUMIF('Cobros Realizados'!$O:$O,$D7,'Cobros Realizados'!$P:$P)
    Pendiente  =Total-Ejecutado
    Proveedor  =-SUMIFS(Proveedores!$S:$S,Proveedores!$F:$F,$D62,
                        Proveedores!$W:$W,"<"&$G$2)

Las columnas clave de las subpestanas estan DONDE EL LAS USA: cliente en B
e importe en K en 'Clientes (Nuevos)'; cliente en O e importe en P en
'Cobros Realizados'; proveedor en F, pendiente en S y mes en W en
'Proveedores'; proveedor en H e importe en L en 'Pagos Realizados'. Asi sus
formulas de siempre funcionan si anade filas o cruza contra su libro.

Todo se rellena desde Holded en cada actualizacion. Si toca una subpestana,
la maestra recalcula sola al abrir: eso es "todo linkado".
============================================================================
"""
from __future__ import annotations

from datetime import date

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

AZUL = "1F4D5C"
GRIS = "F1F4F5"
FMT = "#,##0"

f_tit = Font(bold=True, size=14)
f_cab = Font(bold=True, color="FFFFFF")
f_neg = Font(bold=True)
f_gris = Font(color="6B7680", size=9)
r_cab = PatternFill("solid", fgColor=AZUL)
r_sub = PatternFill("solid", fgColor=GRIS)


def _anchos(ws, anchos):
    for j, a in enumerate(anchos, start=1):
        ws.column_dimensions[get_column_letter(j)].width = a


def _cab(ws, fila, textos, desde=1):
    for j, t in enumerate(textos, start=desde):
        c = ws.cell(fila, j, t)
        c.font = f_cab
        c.fill = r_cab


def _n(ws, fila, col, v):
    c = ws.cell(fila, col, v)
    if not (isinstance(v, str) and not v.startswith("=")):
        c.number_format = FMT
    return c


def _sub(ws, fila, hasta_col):
    for j in range(1, hasta_col + 1):
        ws.cell(fila, j).fill = r_sub
        ws.cell(fila, j).font = f_neg


# ---------------------------------------------------------------------------
def _hoja_cobros(wb, dc, cobrado_mes_fac, cobrabilidad):
    """
    'Cobros': el pivot por cliente que alimenta el VLOOKUP de la maestra
    (A cliente, B pendiente al inicio del mes) y debajo de las columnas
    de resumen, nada: el detalle factura a factura va en su propia hoja.

    B es el pendiente AL INICIO DEL MES, reconstruido como pendiente de hoy
    mas lo cobrado en el mes. Asi la maestra hace su cuenta de siempre
    (Forecast - Ejecutado = Pendiente) y el pendiente que sale es EXACTO al
    de hoy: la resta no es aproximada, es identidad.
    """
    ws = wb.create_sheet("Cobros")
    _cab(ws, 1, ["Cliente", "Pendiente inicio mes", "Cobrado en el mes",
                 "Pendiente hoy", "Vencido hoy", "Sin vencer",
                 "Cobrable según motor"])
    entra_cli = {}
    if cobrabilidad is not None:
        dfc, _ = cobrabilidad
        if dfc is not None and not dfc.empty:
            for cl, g in dfc.groupby("cliente"):
                entra_cli[cl] = float(g[g["entra"]]["pendiente_cobro"].sum())
    f = 2
    if dc is not None and not dc.empty:
        e = dc.copy()
        e["pend_hoy"] = e["teorico_hoy"] - e["liquidado"]
        e["cob_mes"] = e["num"].map(lambda n: cobrado_mes_fac.get(str(n), 0.0))
        e["venc"] = e["retraso"].clip(lower=0)
        g = e.groupby("cliente").agg(
            pend_hoy=("pend_hoy", "sum"), cob_mes=("cob_mes", "sum"),
            venc=("venc", "sum"), total=("total", "sum"),
            teor=("teorico_hoy", "sum"), liq=("liquidado", "sum")).reset_index()
        g["inicio"] = g["pend_hoy"] + g["cob_mes"]
        g = g[(g["inicio"].abs() > 0.01) | (g["pend_hoy"].abs() > 0.01)]
        for _, r in g.sort_values("inicio", ascending=False).iterrows():
            ws.cell(f, 1, r["cliente"])
            _n(ws, f, 2, round(r["inicio"], 2))
            _n(ws, f, 3, round(r["cob_mes"], 2))
            _n(ws, f, 4, f"=B{f}-C{f}")
            _n(ws, f, 5, round(r["venc"], 2))
            _n(ws, f, 6, round(max(0.0, r["total"] - max(r["teor"], r["liq"])), 2))
            _n(ws, f, 7, round(entra_cli.get(r["cliente"], r["pend_hoy"]), 2))
            f += 1
    _anchos(ws, [42, 18, 16, 14, 13, 13, 13])
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:G{max(2, f - 1)}"
    return f - 1


def _hoja_cobros_fac(wb, dc, cobrado_mes_fac):
    ws = wb.create_sheet("Cobros (Facturas)")
    _cab(ws, 1, ["Cliente", "Factura", "Vencimiento", "Total",
                 "Debería cobrado (Eli)", "Cobrado total", "Cobrado en el mes",
                 "Vencido", "Sin vencer"])
    f = 2
    if dc is not None and not dc.empty:
        e = dc.copy()
        e["venc"] = e["retraso"].clip(lower=0)
        act = e[(e["teorico_hoy"].abs() > 0.01) | (e["liquidado"].abs() > 0.01)
                | (e["total"].abs() > 0.01)]
        for _, r in act.sort_values(["cliente", "venc"],
                                    ascending=[True, False]).iterrows():
            ws.cell(f, 1, r["cliente"])
            ws.cell(f, 2, str(r["num"]))
            ws.cell(f, 3, str(r.get("vencimiento") or ""))
            _n(ws, f, 4, round(float(r["total"]), 2))
            _n(ws, f, 5, round(float(r["teorico_hoy"]), 2))
            _n(ws, f, 6, round(float(r["liquidado"]), 2))
            _n(ws, f, 7, round(cobrado_mes_fac.get(str(r["num"]), 0.0), 2))
            _n(ws, f, 8, round(float(r["venc"]), 2))
            _n(ws, f, 9, round(max(0.0, float(r["total"])
                                   - max(float(r["teorico_hoy"]),
                                         float(r["liquidado"]))), 2))
            f += 1
    _anchos(ws, [40, 15, 12, 12, 17, 13, 15, 12, 12])
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:I{max(2, f - 1)}"


def _hoja_nuevos(wb, rent, detalle):
    """
    'Clientes (Nuevos)': cliente en B e importe en K, que son las columnas
    que usa su SUMIFS de toda la vida. Rentings del calendario de Eli sin
    factura en Holded, ventas de la fusion LML y ventas aun sin facturar.
    """
    ws = wb.create_sheet("Clientes (Nuevos)")
    ws.cell(1, 1, "Cliente en B e importe en K: las columnas del SUMIFS "
                  "de la maestra. Añade filas y la maestra las recoge."
            ).font = f_gris
    _cab(ws, 2, ["", "Cliente", "Tipo", "Mes", "", "", "", "", "", "",
                 "Importe"], desde=1)
    f = 3
    if rent is not None and not rent.empty:
        for _, r in rent.sort_values("importe", ascending=False).iterrows():
            ws.cell(f, 2, r["cliente"])
            ws.cell(f, 3, "Venta fusión LML" if r.get("tipo") == "fusion"
                    else "Renting sin factura")
            ws.cell(f, 4, str(r["mes"]))
            _n(ws, f, 11, round(float(r["importe"]), 2))
            f += 1
    for x in (detalle or {}).get("sin_facturar") or []:
        ws.cell(f, 2, x.get("concepto", ""))
        ws.cell(f, 3, "Sin facturar")
        _n(ws, f, 11, round(x["unidades"] * x["precio"] * (1 + x["iva"]), 2))
        f += 1
    _anchos(ws, [3, 42, 20, 10, 3, 3, 3, 3, 3, 3, 14])
    ws.freeze_panes = "A3"


def _hoja_realizados(wb, rea, sentido, titulo, col_nombre, col_importe):
    """
    Cobros/Pagos realizados con el tercero y el importe en LAS COLUMNAS QUE
    EL YA USA: O/P en cobros, H/L en pagos. Sus SUMIF siguen funcionando.
    """
    ws = wb.create_sheet(titulo)
    ncols = max(col_importe, col_nombre)
    cab = [""] * ncols
    cab[0:4] = ["Fecha", "Factura", "Banco", "Concepto"]
    cab[col_nombre - 1] = "Cliente" if sentido == "cobro" else "Proveedor"
    cab[col_importe - 1] = "Importe"
    _cab(ws, 1, cab)
    f = 2
    if rea is not None and not rea.empty:
        d = rea[rea["sentido"] == sentido]
        for _, r in d.sort_values("fecha").iterrows():
            ws.cell(f, 1, str(r["fecha"]))
            ws.cell(f, 2, str(r["num"]))
            ws.cell(f, 3, str(r.get("banco") or ""))
            ws.cell(f, 4, str(r.get("concepto") or "")[:80])
            ws.cell(f, col_nombre, r["tercero"])
            _n(ws, f, col_importe, round(float(r["importe"]), 2))
            f += 1
    anchos = [11, 15, 22, 34] + [3] * (ncols - 6) + [40, 13]
    _anchos(ws, anchos[:ncols])
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(ncols)}{max(2, f - 1)}"


def _hoja_proveedores(wb, dp, pagado_mes_fac):
    """
    'Proveedores': proveedor en F, pendiente en S y mes de vencimiento en W,
    las columnas de su -SUMIFS. S es el pendiente AL INICIO DEL MES
    (pendiente hoy + pagado en el mes sobre esa factura), por la misma
    identidad que en Cobros: Forecast - Ejecutado = Pendiente exacto.
    """
    ws = wb.create_sheet("Proveedores")
    cab = [""] * 23
    cab[0:5] = ["Factura", "Fecha venc.", "Tipología", "Estado", ""]
    cab[5] = "Proveedor"                       # F
    cab[18] = "Pendiente inicio mes"           # S
    cab[19] = "Pagado en el mes"               # T
    cab[20] = "Pendiente hoy"                  # U
    cab[22] = "Mes venc. (YYYYMM)"             # W
    _cab(ws, 1, cab)
    f = 2
    if dp is not None and not dp.empty:
        e = dp.copy()
        e["pag_mes"] = e["num"].map(lambda n: pagado_mes_fac.get(str(n), 0.0))
        act = e[(e["pendiente"].abs() > 0.01) | (e["pag_mes"].abs() > 0.01)]
        for _, r in act.sort_values(["proveedor", "vencimiento"]).iterrows():
            v = r.get("vencimiento")
            ws.cell(f, 1, str(r["num"]))
            ws.cell(f, 2, str(v or ""))
            ws.cell(f, 3, str(r.get("tipologia") or ""))
            ws.cell(f, 4, "VENCIDO" if r.get("vencido") else str(r.get("estado") or ""))
            ws.cell(f, 6, r["proveedor"])
            _n(ws, f, 19, round(float(r["pendiente"]) + r["pag_mes"], 2))
            _n(ws, f, 20, round(r["pag_mes"], 2))
            _n(ws, f, 21, f"=S{f}-T{f}")
            if hasattr(v, "year"):
                ws.cell(f, 23, v.year * 100 + v.month)
            f += 1
    _anchos(ws, [15, 12, 14, 12, 3, 40] + [3] * 12 + [18, 14, 13, 3, 16])
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:W{max(2, f - 1)}"


def _hoja_bancos(wb, bk, mec):
    ws = wb.create_sheet("Bancos")
    ws.cell(1, 1, "Bottom Up - banco a banco").font = f_tit
    _cab(ws, 3, ["Cuenta", "Al empezar el mes", "Hoy", "Variación", "Movs"])
    f = 4
    pc = (bk or {}).get("por_cuenta") or []
    for x in pc:
        ws.cell(f, 1, x["cuenta"])
        _n(ws, f, 2, round(x["inicio"], 2))
        _n(ws, f, 3, round(x["hoy"], 2))
        _n(ws, f, 4, f"=C{f}-B{f}")
        ws.cell(f, 5, x["n"])
        f += 1
    if pc:
        ws.cell(f, 1, "TOTAL")
        for col in "BCD":
            _n(ws, f, ord(col) - 64, f"=SUM({col}4:{col}{f-1})")
        _sub(ws, f, 5)
        f += 1
    f += 1
    cn = (mec or {}).get("concil") or {}
    _cab(ws, f, ["El levered, contra los bancos", "Importe"]); f += 1
    fila_contable = f
    for nombre, v in [("LEVERED ejecutado = variación contable de bancos",
                       cn.get("contable")),
                      ("Pendiente de conciliar del mes (con signo)",
                       cn.get("pendiente")),
                      ("Descuadre restante", cn.get("descuadre"))]:
        ws.cell(f, 1, nombre)
        _n(ws, f, 2, round(float(v or 0), 2))
        f += 1
    ws.cell(f, 1, "= Variación de saldos bancarios (día 1 → hoy)")
    _n(ws, f, 2, f"=SUM(B{fila_contable}:B{f-1})")
    _sub(ws, f, 2)
    f += 2
    _cab(ws, f, ["Pagos de deuda del mes", "Importe"]); f += 1
    ini_deu = f
    for x in (bk or {}).get("detalle_deuda") or []:
        ws.cell(f, 1, f"{x['cuenta']} {x['nombre'] or 'deuda'}")
        _n(ws, f, 2, round(float(x["importe"]), 2))
        f += 1
    ws.cell(f, 1, "TOTAL deuda")
    _n(ws, f, 2, f"=SUM(B{ini_deu}:B{f-1})" if f > ini_deu else 0)
    _sub(ws, f, 2)
    _anchos(ws, [52, 18, 16, 14, 8])
    return f  # fila del total de deuda


def _hoja_forecast(wb, fc):
    ws = wb.create_sheet("Forecast")
    meses = fc["meses"]
    _cab(ws, 1, ["Concepto"] + [fc["lineas"][m]["etiqueta"] for m in meses])
    CLAVES = [("Cobro clientes", "cobro_clientes"),
              ("Rentings sin factura", "rentings_sin_factura"),
              ("Ventas fusión LML", "ventas_fusion_lml"),
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
    f = 2
    for nombre, k in CLAVES:
        ws.cell(f, 1, nombre)
        for j, m in enumerate(meses, start=2):
            _n(ws, f, j, round(float(fc["lineas"][m].get(k, 0) or 0), 2))
        if k in ("cash_in", "cash_out", "fcf", "saldo_proyectado"):
            _sub(ws, f, len(meses) + 1)
        f += 1
    _anchos(ws, [26] + [15] * len(meses))


# ---------------------------------------------------------------------------
def generar(ruta, fc, cuadre, meta) -> None:
    mec = meta.get("mes_en_curso") or {}
    dc = fc.get("detalle_cobros")
    dp = fc.get("detalle_pagos")
    rea = meta.get("realizados")
    rent = fc.get("rentings")
    eje = fc.get("ejecutado") or {}
    bk = eje.get("banco") or {}
    mes0 = fc["meses"][0]
    mes1 = fc["meses"][1] if len(fc["meses"]) > 1 else str(int(mes0) + 1)

    # lo cobrado/pagado en el mes, POR FACTURA, para reconstruir el pendiente
    # al inicio del mes (pendiente hoy + movido en el mes = inicio)
    cob_fac, pag_fac = {}, {}
    if rea is not None and not rea.empty:
        for _, r in rea.iterrows():
            k = str(r["num"])
            if r["sentido"] == "cobro":
                cob_fac[k] = cob_fac.get(k, 0.0) + float(r["importe"])
            elif r["sentido"] == "pago":
                pag_fac[k] = pag_fac.get(k, 0.0) + float(r["importe"])

    wb = Workbook()
    ws = wb.active
    ws.title = "Forecast Caja - Mes en Curso"

    # ---- subpestanas primero (la maestra las referencia) ------------------
    _hoja_cobros(wb, dc, cob_fac, meta.get("cobrabilidad"))
    _hoja_cobros_fac(wb, dc, cob_fac)
    _hoja_nuevos(wb, rent[rent["mes"] == mes0] if rent is not None
                 and not rent.empty else rent, fc.get("detalle"))
    _hoja_realizados(wb, rea, "cobro", "Cobros Realizados", 15, 16)   # O, P
    _hoja_realizados(wb, rea, "pago", "Pagos Realizados", 8, 12)      # H, L
    _hoja_proveedores(wb, dp, pag_fac)
    _hoja_bancos(wb, bk, mec)
    _hoja_forecast(wb, fc)

    # ---- la maestra, con formulas ----------------------------------------
    ws.cell(1, 1, f"Forecast Caja - {mec.get('etiqueta', mes0)}").font = f_tit
    ws.cell(2, 1, "Generado desde Holded el "
            f"{date.today():%d/%m/%Y}. Todo va con fórmulas sobre las "
            "subpestañas: si tocas una subpestaña, esto recalcula al abrir.")
    ws.cell(2, 1).font = f_gris
    ws.cell(2, 6, "Mes"); ws.cell(2, 6).font = f_neg
    ws.cell(2, 7, int(mes0)); ws.cell(2, 8, "Mes sig."); ws.cell(2, 8).font = f_neg
    ws.cell(2, 9, int(mes1))
    _cab(ws, 3, ["", "Cert.", "", "Concepto", "", "Forecast", "Adicional",
                 "Total", "Ejecutado", "Pendiente"])

    def fila_cliente(f, nombre, cert):
        ws.cell(f, 1, nombre)
        ws.cell(f, 2, cert)
        ws.cell(f, 4, nombre)
        _n(ws, f, 6, f"=IFERROR(VLOOKUP($D{f},Cobros!$A:$B,2,0),0)")
        _n(ws, f, 7, "=SUMIFS('Clientes (Nuevos)'!$K:$K,"
                     f"'Clientes (Nuevos)'!$B:$B,$D{f})")
        _n(ws, f, 8, f"=F{f}+G{f}")
        _n(ws, f, 9, "=SUMIF('Cobros Realizados'!$O:$O,"
                     f"$D{f},'Cobros Realizados'!$P:$P)")
        _n(ws, f, 10, f"=H{f}-I{f}")

    def fila_proveedor(f, nombre):
        ws.cell(f, 1, nombre)
        ws.cell(f, 2, 4)
        ws.cell(f, 4, nombre)
        _n(ws, f, 6, f"=-SUMIFS(Proveedores!$S:$S,Proveedores!$F:$F,$D{f},"
                     f"Proveedores!$W:$W,\"<\"&$I$2)")
        _n(ws, f, 7, 0)
        _n(ws, f, 8, f"=F{f}+G{f}")
        _n(ws, f, 9, "=SUMIFS('Pagos Realizados'!$L:$L,"
                     f"'Pagos Realizados'!$H:$H,$D{f})")
        _n(ws, f, 10, f"=H{f}-I{f}")

    def fila_valores(f, concepto, ejec, pend, cert=""):
        # Forecast = mes completo (ejecutado + pendiente), para que TODAS las
        # filas signifiquen lo mismo: Total = mes, Ejecutado = hecho,
        # Pendiente = Total - Ejecutado. Mezclar semanticas por bloque es lo
        # que hace ilegible una maestra.
        ws.cell(f, 2, cert)
        ws.cell(f, 4, concepto)
        _n(ws, f, 6, round(float(ejec) + float(pend), 2))
        _n(ws, f, 7, 0)
        _n(ws, f, 8, f"=F{f}+G{f}")
        _n(ws, f, 9, round(float(ejec), 2))
        _n(ws, f, 10, f"=H{f}-I{f}")

    # -- clientes: union de los del pivot Cobros y los de Clientes (Nuevos) --
    clientes, cert_cli = [], {}
    if dc is not None and not dc.empty:
        e = dc.copy()
        e["pend_hoy"] = e["teorico_hoy"] - e["liquidado"]
        e["cob_mes"] = e["num"].map(lambda n: cob_fac.get(str(n), 0.0))
        e["ini"] = e["pend_hoy"] + e["cob_mes"]
        g = e.groupby("cliente").agg(ini=("ini", "sum")).reset_index()
        g = g[g["ini"].abs() > 0.01].sort_values("ini", ascending=False)
        clientes = list(g["cliente"])
        if "certidumbre" in e.columns:
            cert_cli = e.groupby("cliente")["certidumbre"].max().to_dict()
    if rent is not None and not rent.empty:
        for c in rent[rent["mes"] == mes0]["cliente"].unique():
            if c not in clientes:
                clientes.append(c)

    f = 4
    fila_cashin = f
    f += 1
    ini_cli = f
    ws.cell(f - 1, 4, "Cobro Clientes"); ws.cell(f - 1, 2, "")
    for c in clientes:
        fila_cliente(f, c, int(cert_cli.get(c, 2)))
        f += 1
    fin_cli = f - 1
    fila_tot_cli = fila_cashin  # el total de clientes vive en la fila Cash IN? no:
    # total del bloque de clientes en su propia fila
    filas_extra_in = []
    tot_cli = f
    ws.cell(f, 4, "Total Cobro Clientes")
    for col in "FGHIJ":
        _n(ws, f, ord(col) - 64 if col <= "J" else 0,
           f"=SUM({col}{ini_cli}:{col}{fin_cli})")
    _sub(ws, f, 10)
    f += 1
    # ajustes que en su hoja son filas sueltas del Cash IN
    det = fc.get("detalle") or {}
    aj = det.get("ajustes") or []
    for x in aj:
        fila_valores(f, x["concepto"], 0, x["importe"])
        filas_extra_in.append(f)
        f += 1
    m0L = fc["lineas"][mes0]
    if abs(m0L.get("impuestos", 0) or 0) > 0.005:
        fila_valores(f, "(+) Impuestos", 0, m0L["impuestos"])
        filas_extra_in.append(f)
        f += 1
    # Cash IN total
    ws.cell(fila_cashin, 4, "Cash IN")
    for col in "FGHIJ":
        extras = "".join(f"+{col}{x}" for x in filas_extra_in)
        _n(ws, fila_cashin, ord(col) - 64, f"={col}{tot_cli}{extras}")
    _sub(ws, fila_cashin, 10)

    # -- Cash OUT -----------------------------------------------------------
    f += 1
    fila_cashout = f
    f += 1
    ws.cell(f - 1, 4, "")
    proveedores = []
    if dp is not None and not dp.empty:
        e = dp.copy()
        e["pag_mes"] = e["num"].map(lambda n: pag_fac.get(str(n), 0.0))
        e["ini"] = e["pendiente"] + e["pag_mes"]
        # solo lo que vence hasta fin del mes en curso entra en la maestra;
        # el SUMIFS ya filtra por W < mes siguiente, aqui solo elegimos filas
        g = e.groupby("proveedor").agg(ini=("ini", "sum")).reset_index()
        proveedores = list(g[g["ini"].abs() > 0.01]
                           .sort_values("ini", ascending=False)["proveedor"])
    ini_prov = f
    ws.cell(f - 1, 4, "Pago Proveedores")
    for p in proveedores:
        fila_proveedor(f, p)
        f += 1
    fin_prov = f - 1
    tot_prov = f
    ws.cell(f, 4, "Total Pago Proveedores")
    for col in "FGHIJ":
        _n(ws, f, ord(col) - 64, f"=SUM({col}{ini_prov}:{col}{fin_prov})")
    _sub(ws, f, 10)
    f += 1

    filas_fijos = []
    mapa_fijos = {"Salarios y seguridad social": "salarios",
                  "Impuestos": "impuestos",
                  "Cuotas sale & leaseback": "sl",
                  "Recurrentes y otros fijos": None,
                  "Cuotas de tarjeta ya cargadas": "tarjetas",
                  "Otros pagos (comisiones, traspasos, varios)": "otros_pag"}
    for x in mec.get("cash_out") or []:
        if x["concepto"] == "Pago proveedores":
            continue
        fila_valores(f, x["concepto"], x["ejecutado"], x["pendiente"])
        filas_fijos.append(f)
        f += 1
    ws.cell(fila_cashout, 4, "Cash OUT (sin deuda)")
    for col in "FGHIJ":
        extras = "".join(f"+{col}{x}" for x in filas_fijos)
        _n(ws, fila_cashout, ord(col) - 64, f"={col}{tot_prov}{extras}")
    _sub(ws, fila_cashout, 10)

    # -- unlevered -> deuda -> levered --------------------------------------
    f += 1
    fila_unlev = f
    ws.cell(f, 4, "UNLEVERED FCF")
    for col in "FGHIJ":
        _n(ws, f, ord(col) - 64,
           f"={col}{fila_cashin}+{col}{fila_cashout}")
    _sub(ws, f, 10)
    f += 1
    fd = mec.get("deuda") or {}
    ws.cell(f, 4, "Pagos de deuda (detalle en la hoja Bancos)")
    _n(ws, f, 6, round(float(fd.get("ejecutado", 0) or 0), 2))
    _n(ws, f, 7, 0)
    _n(ws, f, 8, f"=F{f}+G{f}")
    _n(ws, f, 9, round(float(fd.get("ejecutado", 0) or 0), 2))
    _n(ws, f, 10, f"=H{f}-I{f}")
    fila_deuda = f
    f += 1
    ws.cell(f, 4, "LEVERED FCF (= variación de caja)")
    for col in "FGHIJ":
        _n(ws, f, ord(col) - 64,
           f"={col}{fila_unlev}+{col}{fila_deuda}")
    _sub(ws, f, 10)
    fila_lev = f
    f += 2

    # -- saldos y conciliacion ----------------------------------------------
    ws.cell(f, 4, "Saldo hoy")
    _n(ws, f, 6, round(float(mec.get("saldo_hoy", 0) or 0), 2))
    ws.cell(f, 4).font = f_neg
    f += 1
    ws.cell(f, 4, "+ Pendiente del mes (LEVERED col. Pendiente)")
    _n(ws, f, 6, f"=J{fila_lev}")
    f += 1
    ws.cell(f, 4, "= Saldo proyectado a cierre")
    _n(ws, f, 6, f"=F{f-2}+F{f-1}")
    _sub(ws, f, 6)
    f += 2
    ws.cell(f, 4, "El levered ejecutado contra la variación de bancos: "
                  "hoja Bancos. El detalle de deuda, también.")
    ws.cell(f, 4).font = f_gris

    _anchos(ws, [34, 6, 2, 46, 2, 14, 12, 14, 14, 14])
    ws.freeze_panes = "A4"

    # ---- leeme ------------------------------------------------------------
    ws = wb.create_sheet("Léeme")
    for i, t in enumerate([
        "Cómo funciona este fichero",
        "",
        "La maestra 'Forecast Caja - Mes en Curso' calcula con FÓRMULAS sobre",
        "las subpestañas, con tu propia estructura: Forecast (VLOOKUP a Cobros),",
        "Adicional (SUMIFS a 'Clientes (Nuevos)' col. B/K), Ejecutado (SUMIF a",
        "'Cobros Realizados' col. O/P y 'Pagos Realizados' col. H/L), y",
        "proveedores con -SUMIFS a 'Proveedores' col. F/S/W.",
        "",
        "Todo sale de Holded en cada actualización. La columna 'Forecast' es el",
        "pendiente AL INICIO del mes (pendiente hoy + movido en el mes), así",
        "Total - Ejecutado = pendiente de hoy al euro, no aproximado.",
        "",
        "Si tocas una subpestaña (añadir una fila en 'Clientes (Nuevos)', p.ej.),",
        "la maestra recalcula al abrir. En la siguiente actualización el fichero",
        "se regenera desde Holded: lo que quieras fijar, llévalo a config.yaml",
        "(previsiones) o edítalo en tu copia local.",
    ], start=1):
        ws.cell(i, 1, t)
        if i == 1:
            ws.cell(i, 1).font = f_tit
    _anchos(ws, [96])

    wb.save(ruta)
