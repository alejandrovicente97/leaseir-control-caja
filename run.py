#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================================
 LEASEIR - Orquestador: datos -> forecast -> dashboard
============================================================================
   python run.py                      usa lo que encuentre (Holded si existe)
   python run.py --fuente excel       fuerza los Excel de la carpeta
   python run.py --mes 202607         fija el mes en curso
============================================================================
"""
from __future__ import annotations
import argparse, sys
from datetime import date
from pathlib import Path

import yaml

from fuentes import desde_excel, desde_holded, calendario_cobros
from motor import MotorCaja
from dashboard import construir

RAIZ = Path(__file__).resolve().parent


def localizar(base: Path) -> tuple[Path | None, Path | None]:
    """Coge el Forecast y el Control de Cobros mas recientes de la carpeta."""
    fc = sorted(base.glob("8. Forecast Caja/**/*Forecast CashFlow*.xlsx"))
    co = sorted(base.glob("7. Control de Cobros/**/Control de cobros - New Template*.xlsx"))
    return (fc[-1] if fc else None), (co[-1] if co else None)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="/mnt/user-data/uploads/19. Control Caja")
    ap.add_argument("--fuente", choices=["auto", "holded", "excel"], default="auto")
    ap.add_argument("--mes", default=None)
    ap.add_argument("--holded", default=None, help="ruta a holded.json")
    ap.add_argument("--calendario", default=None,
                    help="xlsx con el calendario de Eli; 'drive' lo baja de Google")
    ap.add_argument("--salida", default=str(RAIZ / "caja_leaseir.html"))
    ap.add_argument("--config", default=str(RAIZ / "config.yaml"))
    args = ap.parse_args()

    cfg = yaml.safe_load(open(args.config, encoding="utf-8"))
    base = Path(args.base)
    f_forecast, f_cobros = localizar(base)
    json_holded = base / "_data_holded" / "holded.json"

    calidad = []

    # ---- fuente ----------------------------------------------------------
    if args.holded:
        json_holded = Path(args.holded)
    usar_holded = args.fuente == "holded" or (args.fuente == "auto" and json_holded.exists())
    if usar_holded:
        if not json_holded.exists():
            sys.exit(f"No existe {json_holded}. Ejecuta holded_extract.py primero.")
        datos = desde_holded(json_holded)
    else:
        if not (f_forecast and f_cobros):
            sys.exit(f"No encuentro los Excel bajo {base}")
        datos = desde_excel(f_cobros, f_forecast)
        calidad.append("Datos leidos de los Excel de la carpeta, no de la API de Holded. "
                       "Los movimientos de tesoreria no estan disponibles, asi que el "
                       "cuadre de caja queda a medias.")

    # ---- calendario de cobros de Eli -------------------------------------
    if args.calendario == "drive":
        from google_sheets import calendario_desde_drive
        cal = calendario_desde_drive()
    elif args.calendario:
        cal = calendario_cobros(Path(args.calendario))
    elif f_cobros:
        cal = calendario_cobros(f_cobros)
    else:
        sys.exit("No encuentro el calendario de Eli. Usa --calendario <ruta|drive>.")

    # ---- motor -----------------------------------------------------------
    m = MotorCaja(datos, cal, cfg, mes_actual=args.mes)
    fc = m.forecast()
    cu = m.cuadre()
    alertas = m.alertas(fc)

    # ---- calidad del dato -------------------------------------------------
    if getattr(m, "fuera_de_alcance", 0):
        calidad.append(
            f"{m.fuera_de_alcance} facturas anteriores a {m.mes_inicio} quedan fuera del "
            f"forecast: el calendario de Eli arranca en {m.mes_inicio} y sin cuotas "
            f"cargadas darian falsos anticipos.")
    excl = cfg["cobros"].get("excluir_clientes") or []
    if excl:
        calidad.append("Clientes excluidos del forecast por configuracion: "
                       + ", ".join(excl) + ".")

    # Lo que se aparta del lado de pagos se dice con su importe. Un criterio que
    # mueve 4,4 millones no puede vivir escondido en un fichero de configuracion.
    exc_p = cfg.get("pagos", {}).get("excluir_proveedores") or []
    if exc_p:
        ce = getattr(m, "compras_excluidas", None)
        imp = (ce["pendiente"].sum()
               if ce is not None and not ce.empty and "pendiente" in ce.columns else 0.0)
        n = 0 if ce is None else len(ce)
        # el separador de miles se cambia solo en el importe: hacerlo sobre la
        # frase entera se comia las comas de "Leaseir Medical Light, S.L."
        cifra = f"{abs(imp):,.0f}".replace(",", " ")
        calidad.append(
            f"Proveedores excluidos por intercompania: {', '.join(exc_p)} "
            f"({n} factura{'s' if n != 1 else ''}, {cifra} EUR pendientes). "
            f"Es saldo entre sociedades del grupo, no salida de caja: fuera "
            f"del forecast, pero contabilizado aqui.")
    # Deuda comercial vieja apartada del forecast de pagos: se dice con su
    # importe. Sigue en el ageing y en el pendiente; solo no cuenta como pago
    # del mes. Ocultar 842k sin decirlo seria peor que contarlos.
    ff = (cfg.get("pagos") or {}).get("fuera_del_forecast") or []
    if ff:
        pf = getattr(m, "pagos_fuera_forecast", None)
        imp = (pf["pendiente"].sum()
               if pf is not None and not pf.empty and "pendiente" in pf.columns else 0.0)
        n = 0 if pf is None else len(pf)
        cifra = f"{abs(imp):,.0f}".replace(",", " ")
        calidad.append(
            f"Fuera del forecast de pagos por ser deuda comercial antigua: "
            f"{', '.join(ff)} ({n} factura{'s' if n != 1 else ''}, {cifra} EUR "
            f"pendientes). Sigue en el ageing y en el pendiente de pago; no se "
            f"proyecta como salida de caja del mes.")

    v = m.cobros_por_factura()
    if not v.empty and "en_calendario" in v.columns:
        sin_cal = int((~v["en_calendario"]).sum())
        if sin_cal:
            calidad.append(
                f"{sin_cal} facturas de {m.mes_inicio} en adelante no figuran en el "
                f"calendario de Eli; se toma el vencimiento que trae Holded y, "
                f"si tampoco lo hay, se dan por exigibles hoy. Conviene "
                f"revisarlas con ella.")
        # facturas SIN cuota de Eli cuyo vencimiento lo pone Holded: ya no se
        # dan por exigibles hoy, entran en su mes. Se dice cuantas y cuanto.
        if "origen_venc" in v.columns:
            hv = v[(v["origen_venc"] == "holded") & (v["pendiente"] > 0.01)] \
                if "pendiente" in v.columns else v[v["origen_venc"] == "holded"]
            if len(hv):
                fut = hv[hv["teorico_hoy"] < 0.01]
                calidad.append(
                    f"{len(hv)} facturas sin cuota en el calendario de Eli toman "
                    f"el vencimiento de Holded; {len(fut)} de ellas "
                    f"({fut['total'].sum() - fut['liquidado'].sum():,.0f} EUR) "
                    f"vencen mas adelante y ya no se cuentan como exigibles hoy."
                    .replace(",", " "))
            disc = v[v.get("venc_discrepa", False) == True] if "venc_discrepa" in v.columns else v.iloc[0:0]
            if len(disc):
                calidad.append(
                    f"{len(disc)} facturas con cuota de Eli cuyo vencimiento en "
                    f"Holded es posterior a la ultima cuota. Manda Eli, pero "
                    f"conviene mirar cual de los dos esta mal.")
        neg = v[v["pendiente_cobro"] < -0.01]
        if len(neg):
            calidad.append(
                f"{len(neg)} facturas con cobro por encima del calendario "
                f"({abs(neg['pendiente_cobro'].sum()):,.0f} EUR): anticipos de cliente o "
                f"cuotas mal cargadas en la hoja de Eli.")

    # ---- control de credibilidad del origen -------------------------------
    graves = []
    nv, nc = len(datos["ventas"]), len(datos["compras"])
    if nv == 0:
        graves.append("No ha llegado ninguna factura de venta.")
    elif nv < 50:
        graves.append(f"Solo {nv} facturas de venta: parecen muy pocas.")
    if nc == 0:
        graves.append("No ha llegado ninguna factura de compra.")
    elif nc < 50:
        graves.append(f"Solo {nc} facturas de compra: parecen muy pocas.")
    if datos["bancos"].empty:
        graves.append("Sin cuentas bancarias: la posicion y el cuadre no tienen base.")
    if cal is None or cal.empty:
        graves.append("El calendario de cobros de Eli ha venido vacio.")
    for a in datos.get("avisos_origen") or []:
        calidad.append(f"Aviso de la extraccion: {a}")
    # avisos que levanta el motor al calcular (asiento de apertura, etc.)
    for a in dict.fromkeys(getattr(m, "avisos", []) or []):
        calidad.append(a)
    if graves:
        print("\n  [ATENCION] " + " / ".join(graves))

    meta = {"origen": datos["origen"], "bancos": datos["bancos"], "calidad": calidad,
            "realizados": m.realizados_mes(),
            "check_clientes": m.check_clientes(),
            "cobrabilidad": m.cobrabilidad(),
            # el corte por linea de negocio: manda la hoja Mapping del Sheet de
            # Eli si llega; si no, el snapshot de config (cliente -> linea,
            # cruzado de su propio Control de cobros)
            "mapping_cobros": ((cal.attrs.get("mapping_simple") or {}
                                if hasattr(cal, "attrs") else {})
                               or cfg["cobros"].get("mapping_comercial") or {}),
            "certidumbre": cfg.get("certidumbre") or {},
            "polizas_limites": (cfg.get("tesoreria") or {}).get("polizas") or [],
            # YTD para el Visual Nacho: los meses cerrados del ano en curso
            "unlevered_ytd": sum(
                x.get("unlevered", 0) or 0
                for x in m.serie_unlevered(11)
                if str(x.get("mes", ""))[:4] == (args.mes or f"{date.today():%Y%m}")[:4]),
            "mes_en_curso": m.mes_en_curso(fc),
            # la pantalla de la reunion con Nacho: una pregunta y cinco cifras
            "resumen_nacho": m.resumen_nacho(fc),
            # antiguedad de lo pendiente, cobros y pagos, hasta la factura
            "ageing": m.ageing(),
            "caja_naturaleza": m.caja_por_naturaleza(),
            "serie_unlevered": m.serie_unlevered(6),
            "serie_fcf": m.serie_fcf(6),
            "ocultar_saldo_cero": (cfg.get("tesoreria") or {}).get(
                "ocultar_saldo_cero", True),
            "aviso_limites": (cfg.get("tesoreria") or {}).get("aviso_limites"),
            "problemas_graves": graves,
            "contraste": cfg.get("contraste_excel") or {},
            "cuadre_proyeccion": m.cuadre_proyeccion(fc),
            "url_workflow": (cfg.get("publicacion") or {}).get("url_workflow")}

    # ---- Excel: el fichero de trabajo de Alejandro, con datos vivos -------
    # Va EMBEBIDO en la pagina (data URI): cada recarga trae el Excel de esa
    # actualizacion sin tocar el workflow ni depender de rutas del hosting.
    import base64
    from excel_out import generar as generar_excel
    out = Path(args.salida)
    out.parent.mkdir(parents=True, exist_ok=True)
    xlsx = out.parent / "caja_leaseir.xlsx"
    try:
        generar_excel(xlsx, fc, cu, meta)
        meta["excel_b64"] = base64.b64encode(xlsx.read_bytes()).decode()
        meta["excel_nombre"] = f"Forecast CashFlow Leaseir {date.today():%Y%m%d}.xlsx"
        print(f"Excel         : {xlsx} ({xlsx.stat().st_size / 1024:.0f} KB)")
    except Exception as e:                              # noqa: BLE001
        # el panel no se cae porque el Excel falle, pero el fallo se publica
        calidad.append(f"El Excel de descarga no se ha podido generar: {e}")
        print(f"  [AVISO] excel: {e}")

    # ---- salida ----------------------------------------------------------
    html = construir(fc, cu, alertas, meta)
    out.write_text(html, encoding="utf-8")

    L = fc["lineas"]
    print(f"Fuente        : {datos['origen']}")
    print(f"Mes en curso  : {L[fc['meses'][0]]['etiqueta']}")
    for mm in fc["meses"]:
        x = L[mm]
        print(f"  {x['etiqueta']:>18s}  in {x['cash_in']:>12,.0f}  out {x['cash_out']:>12,.0f}"
              f"  FCF {x['fcf']:>12,.0f}  saldo {x['saldo_proyectado']:>12,.0f}")
    print(f"Alertas       : {len(alertas)}")
    print(f"Dashboard     : {out}")


if __name__ == "__main__":
    main()
