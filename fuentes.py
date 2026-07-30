# -*- coding: utf-8 -*-
"""
============================================================================
 LEASEIR - Capa de fuentes de datos
============================================================================
 Normaliza a un esquema unico los datos vengan de donde vengan:
   - holded.json   (lo que deja el extractor que corre en el PC)
   - los Excel de la carpeta 19. Control Caja  (modo respaldo / validacion)

 Esquema normalizado
 -------------------
 ventas      : num, cliente, cuenta, fecha, vencimiento, total, cobrado,
               pendiente, estado, fecha_cobro, mes_venc
 compras     : num, proveedor, cuenta, fecha, vencimiento, total, pagado,
               pendiente, estado, fecha_pago, mes_venc, tipologia
 calendario  : factura, cliente, mes, importe        (vencimientos de Eli)
 bancos      : cuenta, saldo, tipo ('cuenta' | 'poliza'), limite
============================================================================
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, date
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# utilidades
# ---------------------------------------------------------------------------
def norm(txt) -> str:
    """Normaliza texto para comparar: sin tildes, sin dobles espacios, mayusculas."""
    if txt is None:
        return ""
    s = str(txt).strip()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).upper()


def num(v) -> float:
    """Convierte a float tolerando formatos contables ('  -   EUR', '1.234,56')."""
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return 0.0 if pd.isna(v) else float(v)
    s = str(v).replace("€", "").replace("EUR", "").strip()
    if s in ("", "-", "--"):
        return 0.0
    s = s.replace(".", "").replace(",", ".") if re.search(r",\d{1,2}$", s) else s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return 0.0


def a_fecha(v):
    # pd.NaT es subclase de datetime y su .year es NaN: hay que cazarlo antes
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, (int, float)):          # timestamp unix de Holded
        try:
            return datetime.fromtimestamp(float(v)).date()
        except (OSError, ValueError):
            return None
    s = str(v).strip()[:19]
    for f in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d",
              "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, f).date()
        except ValueError:
            continue
    return None


def mes_de(d) -> str | None:
    d = a_fecha(d)
    if not isinstance(d, (date, datetime)):
        return None
    return f"{d.year}{d.month:02d}"


def suma_meses(mes: str, n: int) -> str:
    a, m = int(mes[:4]), int(mes[4:])
    t = (a * 12 + m - 1) + n
    return f"{t // 12}{t % 12 + 1:02d}"


def nombre_mes(mes: str) -> str:
    MES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
           "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
    return f"{MES[int(mes[4:]) - 1]} {mes[:4]}"


# ===========================================================================
#  FUENTE 1 - HOLDED JSON  (lo que produce holded_extract.py)
# ===========================================================================
def desde_holded(ruta: Path) -> dict:
    with open(ruta, encoding="utf-8") as f:
        d = json.load(f)

    contactos = {c.get("id"): c.get("name") for c in d.get("contactos", [])}

    def documentos(clave, signo=1):
        filas = []
        for doc in d.get(clave, []):
            total = num(doc.get("total")) * signo
            pagado = num(doc.get("paymentsTotal") or doc.get("paid")) * signo
            venc = a_fecha(doc.get("dueDate") or doc.get("date"))
            filas.append({
                "num":         doc.get("docNumber") or doc.get("invoiceNum") or doc.get("id"),
                "tercero":     doc.get("contactName") or contactos.get(doc.get("contact")) or "",
                "cuenta":      (doc.get("desc") or "")[:80],
                "fecha":       a_fecha(doc.get("date")),
                "vencimiento": venc,
                "total":       total,
                "liquidado":   pagado,
                "pendiente":   total - pagado,
                "estado":      "Pagado" if abs(total - pagado) < 0.01 else (
                               "Vencido" if venc and venc < date.today() else "Pendiente"),
                "fecha_liq":   a_fecha(doc.get("paymentDate")),
                "mes_venc":    mes_de(venc),
                "mes_factura": mes_de(a_fecha(doc.get("date"))),
                "tipologia":   (doc.get("tags") or [""])[0] if doc.get("tags") else "",
            })
        return filas

    ventas = documentos("facturas_venta") + documentos("abonos_venta", -1)
    compras = documentos("facturas_compra") + documentos("abonos_compra", -1)

    bancos = []
    for c in d.get("cuentas_tesoreria", []):
        tipo = "poliza" if "poliz" in norm(c.get("name", "")).lower() or c.get("type") == "credit" else "cuenta"
        bancos.append({"cuenta": c.get("name"), "saldo": num(c.get("balance")),
                       "tipo": tipo, "limite": num(c.get("creditLimit"))})

    movs = [{"cuenta": m.get("_cuenta_nombre"), "fecha": a_fecha(m.get("date")),
             "importe": num(m.get("amount")), "concepto": m.get("description") or m.get("concept")}
            for m in d.get("movimientos_tesoreria", [])]

    return {
        "ventas": pd.DataFrame(ventas).rename(columns={"tercero": "cliente"}),
        "compras": pd.DataFrame(compras).rename(columns={"tercero": "proveedor"}),
        "bancos": pd.DataFrame(bancos),
        "movimientos": pd.DataFrame(movs),
        "origen": f"Holded API ({d.get('_meta', {}).get('extraido_en', '?')})",
    }


# ===========================================================================
#  FUENTE 2 - EXCEL de la carpeta (respaldo y validacion)
# ===========================================================================
def _hoja(ruta: Path, hoja: str, fila_cabecera: int) -> pd.DataFrame:
    df = pd.read_excel(ruta, sheet_name=hoja, header=fila_cabecera - 1, engine="openpyxl")
    df.columns = [str(c).strip() for c in df.columns]
    return df


def desde_excel(f_cobros: Path, f_forecast: Path) -> dict:
    # -- facturas de venta (pestana Holded del control de cobros) -----------
    v = _hoja(f_cobros, "Holded", 5)
    ventas = pd.DataFrame({
        "num":         v["Num"],
        "cliente":     v["Cliente"],
        "cuenta":      v["Cuenta"],
        "fecha":       v["Fecha"].map(a_fecha),
        "vencimiento": v["Vencimiento"].map(a_fecha),
        "total":       v["Total"].map(num),
        "liquidado":   v["Cobrado"].map(num),
        "estado":      v["Estado"],
        "fecha_liq":   v["Fecha de cobro"].map(a_fecha),
    }).dropna(subset=["num"])
    ventas["pendiente"] = ventas["total"] - ventas["liquidado"]
    ventas["mes_venc"] = ventas["vencimiento"].map(mes_de)
    ventas["tipologia"] = ""
    # "Ano Mes" es el mes de emision real; la columna Fecha es la de extraccion
    ventas["mes_factura"] = (v["Año Mes"].map(lambda x: str(int(x)) if isinstance(x, (int, float))
                                              and not pd.isna(x) else (str(x)[:6] if x else None))
                             if "Año Mes" in v.columns else None)

    # -- facturas de compra (pestana Proveedores del forecast) --------------
    c = _hoja(f_forecast, "Proveedores", 5)
    compras = pd.DataFrame({
        "num":         c["Num"],
        "proveedor":   c["Proveedor"],
        "cuenta":      c["Cuenta"],
        "fecha":       c["Fecha emisión"].map(a_fecha),
        "vencimiento": c["Vencimiento"].map(a_fecha),
        "total":       c["Total"].map(num),
        "liquidado":   c["Pagado"].map(num),
        "estado":      c["Estado"],
        "fecha_liq":   c["Fecha de pago"].map(a_fecha),
        "tipologia":   c["Tipología"],
    }).dropna(subset=["proveedor"])
    compras["pendiente"] = compras["total"] - compras["liquidado"]
    compras["mes_venc"] = compras["vencimiento"].map(mes_de)

    # -- posicion bancaria (hoja Forecast Caja - Mes en Curso) --------------
    import openpyxl
    wb = openpyxl.load_workbook(f_forecast, read_only=True, data_only=True)
    ws = wb["Forecast Caja - Mes en Curso"]
    bancos = []
    for fila in range(121, 129):                       # cuentas corrientes
        nom, sal = ws.cell(fila, 4).value, ws.cell(fila, 6).value
        if nom and sal is not None:
            bancos.append({"cuenta": str(nom), "saldo": num(sal), "tipo": "cuenta", "limite": 0.0})
    for fila in range(131, 134):                       # polizas de credito
        nom, sal = ws.cell(fila, 4).value, ws.cell(fila, 6).value
        if nom and sal is not None and num(sal) != 0:
            bancos.append({"cuenta": str(nom), "saldo": num(sal), "tipo": "poliza",
                           "limite": num(ws.cell(fila, 3).value)})
    wb.close()

    return {
        "ventas": ventas,
        "compras": compras,
        "bancos": pd.DataFrame(bancos),
        "movimientos": pd.DataFrame(columns=["cuenta", "fecha", "importe", "concepto"]),
        "origen": f"Excel {f_forecast.name}",
    }


# ===========================================================================
#  CALENDARIO DE COBROS DE ELI  (pestana ELISABET / Google Sheet)
# ===========================================================================
def calendario_cobros(ruta: Path, hoja: str = "ELISABET") -> pd.DataFrame:
    """
    La hoja es una matriz factura x mes: cada celda es la cuota que se espera
    cobrar de esa factura en ese mes. La convertimos a formato largo.
    """
    import openpyxl
    wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
    ws = wb[hoja]

    filas = list(ws.iter_rows(values_only=True))
    if not filas:
        return pd.DataFrame(columns=["factura", "cliente", "mes", "importe"])

    cab = filas[0]
    # columnas cuyo encabezado es una fecha -> son los meses del calendario
    meses = {}
    for j, val in enumerate(cab):
        f = a_fecha(val)
        if f and 2020 <= f.year <= 2040:
            meses[j] = f"{f.year}{f.month:02d}"

    registros, presentes = [], set()
    for fila in filas[1:]:
        if len(fila) < 3:
            continue
        cliente, factura = fila[1], fila[2]
        if not factura:
            continue
        # Ojo: una factura puede estar en la hoja SIN calendario (abonos, ventas
        # al contado). Sigue "estando en ELISABET" y hay que distinguirlo de no
        # estar en absoluto: si no, el pendiente de cobro sale negativo.
        presentes.add(norm(factura))
        for j, mes in meses.items():
            if j < len(fila):
                imp = fila[j]
                if isinstance(imp, (int, float)) and imp and abs(imp) > 0.005:
                    registros.append({"factura": str(factura).strip(),
                                      "cliente": str(cliente or "").strip(),
                                      "mes": mes, "importe": float(imp)})
    wb.close()
    df = pd.DataFrame(registros, columns=["factura", "cliente", "mes", "importe"])
    df.attrs["facturas_en_hoja"] = presentes
    return df


def mapping_cuentas(ruta: Path) -> tuple[set, dict]:
    """Devuelve (cuentas que son renting, cuenta -> categoria simple)."""
    import openpyxl
    wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
    ws = wb["Mapping"]
    rentings, simple = set(), {}
    for fila in ws.iter_rows(min_row=3, max_row=300, values_only=True):
        if len(fila) > 2 and fila[2]:
            rentings.add(norm(fila[2]))
        if len(fila) > 6 and fila[5] and fila[6]:
            simple[norm(fila[5])] = str(fila[6]).strip()
    wb.close()
    return rentings, simple


# ===========================================================================
#  CALENDARIO DESDE GOOGLE DRIVE
# ===========================================================================
def calendario_desde_drive(ruta_descargada: Path, hoja: str = "ELISABET") -> pd.DataFrame:
    """
    El fichero de Eli vive en Drive como .xlsx subido
    (https://docs.google.com/spreadsheets/d/1EmO9WHz-ewB8objYRnAvoQ2ZBkhnzAbR).
    Una vez descargado con el conector de Google Drive, se parsea igual que la
    copia local: misma matriz factura x mes, misma pestana ELISABET.
    """
    return calendario_cobros(ruta_descargada, hoja)


ID_SHEET_ELI = "1EmO9WHz-ewB8objYRnAvoQ2ZBkhnzAbR"
