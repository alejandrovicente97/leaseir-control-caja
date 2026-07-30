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
# Esquema canonico. Se declara explicitamente para que un bloque vacio de
# Holded produzca un DataFrame vacio PERO CON COLUMNAS. Sin esto, si un
# endpoint falla el motor casca con KeyError en lugar de dar cero.
COLS_DOC = ["num", "tercero", "cuenta", "fecha", "vencimiento", "total",
            "liquidado", "pendiente", "estado", "estado_api", "fecha_liq",
            "mes_venc", "mes_factura", "tipologia"]
COLS_BANCO = ["cuenta", "saldo", "tipo", "limite"]
COLS_MOV = ["cuenta", "fecha", "importe", "concepto"]


def _pri(d: dict, *claves, defecto=None):
    """Primer valor no vacio de una lista de claves candidatas."""
    for k in claves:
        if k in d and d[k] not in (None, "", []):
            return d[k]
    return defecto


def desde_holded(ruta: Path) -> dict:
    """
    Normaliza el JSON del extractor.

    Los nombres de campo de Holded no son estables entre endpoints ni entre
    versiones, asi que cada dato se busca en varias claves candidatas en vez de
    dar una por segura. Un cambio de nombre en Holded degrada un campo, no
    tumba el forecast.
    """
    with open(ruta, encoding="utf-8") as f:
        d = json.load(f)

    meta = d.get("_meta", {}) or {}
    contactos = {}
    for c in d.get("contactos", []) or []:
        if isinstance(c, dict):
            cid = _pri(c, "id", "_id")
            if cid:
                contactos[cid] = _pri(c, "name", "tradeName", "legalName", defecto="")

    def documentos(clave, signo=1):
        filas = []
        for doc in d.get(clave, []) or []:
            if not isinstance(doc, dict):
                continue
            total = num(_pri(doc, "total", "totalAmount", "amount", defecto=0)) * signo
            cobrado = num(_pri(doc, "paymentsTotal", "paid", "paidAmount", defecto=0)) * signo
            # Holded suele dar el pendiente ya calculado: es mas fiable que restar
            pend_api = _pri(doc, "paymentsPending", "pending", "pendingAmount")
            pendiente = num(pend_api) * signo if pend_api is not None else total - cobrado

            venc = a_fecha(_pri(doc, "dueDate", "duedate", "date"))
            emision = a_fecha(_pri(doc, "date", "issuedDate", "createdAt"))
            f_liq = a_fecha(_pri(doc, "paymentDate", "paidDate", "lastPaymentDate"))
            # si esta cobrada del todo y no hay fecha de cobro, vale el vencimiento
            if f_liq is None and abs(pendiente) < 0.01 and abs(total) > 0.01:
                f_liq = venc

            estado_api = _pri(doc, "status", "state")
            if abs(pendiente) < 0.01 and abs(total) > 0.01:
                estado = "Pagado"
            elif venc and venc < date.today():
                estado = "Vencido"
            else:
                estado = "Pendiente"

            tags = _pri(doc, "tags", defecto=[]) or []
            tag = tags[0] if isinstance(tags, list) and tags else (
                tags if isinstance(tags, str) else "")

            filas.append({
                "num":         _pri(doc, "docNumber", "invoiceNum", "number", "id", defecto=""),
                "tercero":     _pri(doc, "contactName", "contact_name",
                                    defecto=contactos.get(_pri(doc, "contact", "contactId"), "")),
                "cuenta":      str(_pri(doc, "desc", "description", "notes", defecto=""))[:90],
                "fecha":       emision,
                "vencimiento": venc,
                "total":       total,
                "liquidado":   cobrado,
                "pendiente":   pendiente,
                "estado":      estado,
                "estado_api":  estado_api,
                "fecha_liq":   f_liq,
                "mes_venc":    mes_de(venc),
                "mes_factura": mes_de(emision),
                "tipologia":   tag,
            })
        return filas

    ventas = documentos("facturas_venta") + documentos("recibos_venta") \
        + documentos("abonos_venta", -1)
    compras = documentos("facturas_compra") + documentos("abonos_compra", -1)

    # ---- posicion bancaria ------------------------------------------------
    bancos = []
    for c in d.get("cuentas_tesoreria", []) or []:
        if not isinstance(c, dict):
            continue
        nombre = _pri(c, "name", "alias", "description", defecto="(sin nombre)")
        tipo_api = str(_pri(c, "type", "accountType", defecto="")).lower()
        es_poliza = ("poliz" in norm(nombre).lower() or "credit" in tipo_api
                     or "linea" in norm(nombre).lower())
        bancos.append({
            "cuenta": nombre,
            "saldo": num(_pri(c, "balance", "currentBalance", "amount", defecto=0)),
            "tipo": "poliza" if es_poliza else "cuenta",
            "limite": num(_pri(c, "creditLimit", "limit", defecto=0)),
        })

    movs = []
    for m in d.get("movimientos_tesoreria", []) or []:
        if not isinstance(m, dict):
            continue
        movs.append({
            "cuenta": m.get("_cuenta_nombre"),
            "fecha": a_fecha(_pri(m, "date", "valueDate", "createdAt")),
            "importe": num(_pri(m, "amount", "value", "total", defecto=0)),
            "concepto": _pri(m, "description", "concept", "desc", defecto=""),
        })

    sello = meta.get("extraido_en", "?")
    return {
        "ventas": pd.DataFrame(ventas, columns=COLS_DOC).rename(
            columns={"tercero": "cliente"}),
        "compras": pd.DataFrame(compras, columns=COLS_DOC).rename(
            columns={"tercero": "proveedor"}),
        "bancos": pd.DataFrame(bancos, columns=COLS_BANCO),
        "movimientos": pd.DataFrame(movs, columns=COLS_MOV),
        "origen": f"API de Holded ({sello})",
        "avisos_origen": meta.get("avisos", []),
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
