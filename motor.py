# -*- coding: utf-8 -*-
"""
============================================================================
 LEASEIR - Motor de forecast de caja
============================================================================
 Reproduce la logica del Excel "Forecast CashFlow" pero calculada, no a mano:

   CASH IN
     + Cobro de clientes            facturas Holded x calendario de Eli
     + Rentings sin facturar        cuotas del calendario sin factura emitida
     + Ventas comprometidas         parametro (Elha, etc.)
     +/- Ajustes                    parametro

   CASH OUT
     - Pago a proveedores           facturas Holded, acumuladas por vencimiento
     - Salarios                     parametro (no estan en Holded)
     - Cuotas S&L                   parametro / deducidas de Holded
     - Gastos recurrentes           proyectados donde no hay factura
     - Otros fijos                  parametro

   = Unlevered Free Cash Flow

 Y el cuadre:  cobros - pagos del mes  ==  saldo final - saldo inicial
============================================================================
"""
from __future__ import annotations

import re
from datetime import date
from collections import defaultdict

import pandas as pd

from fuentes import norm, mes_de, suma_meses, nombre_mes


def _ejercicio(num, fecha) -> str:
    """
    Ejercicio de la factura a partir de su numero: SInv26-2026001466 -> '2026',
    CN260009 -> '2026'. La columna Fecha del export de Holded es la fecha de
    extraccion, no la de emision, asi que no sirve como criterio principal.
    """
    m = re.search(r"[A-Za-z]+\s*(\d{2})", str(num or ""))
    if m:
        return f"20{m.group(1)}"
    return (mes_de(fecha) or "9999")[:4]


class MotorCaja:

    def __init__(self, datos: dict, calendario: pd.DataFrame, cfg: dict,
                 mes_actual: str | None = None):
        self.d = datos
        self.cal = calendario if calendario is not None else pd.DataFrame(
            columns=["factura", "cliente", "mes", "importe"])
        self.cfg = cfg
        hoy = date.today()
        self.mes = mes_actual or f"{hoy.year}{hoy.month:02d}"
        self.meses = [self.mes] + [suma_meses(self.mes, i)
                                   for i in range(1, cfg["forecast"]["meses_adelante"] + 1)]
        self.ventas = datos["ventas"].copy()
        self.compras = datos["compras"].copy()
        self.avisos: list[str] = []

        # Intercompania del lado de PAGOS. Leaseir Medical Light aparece en
        # Holded como proveedor con 4,45 millones pendientes en 93 facturas:
        # el 96% de todo el vencido. No es caja, es saldo entre sociedades del
        # grupo, y metido en el forecast convertia un julio de +186 mil en uno
        # de -4,27 millones. Ya se excluia del lado de cobros; hacerlo solo en
        # un lado era lo que descuadraba.
        # Se aparta, no se borra: el importe se publica en calidad del dato.
        self.compras_excluidas = pd.DataFrame()
        fuera = {norm(p) for p in (cfg.get("pagos") or {}).get("excluir_proveedores") or []}
        if fuera and not self.compras.empty and "proveedor" in self.compras.columns:
            marca = self.compras["proveedor"].map(norm).isin(fuera)
            self.compras_excluidas = self.compras[marca].copy()
            self.compras = self.compras[~marca].copy()

    # =======================================================================
    #  COBROS
    # =======================================================================
    def cobros_por_factura(self) -> pd.DataFrame:
        """
        Equivalente al 'Cuadro de Control'. Una fila por factura de venta.

        La clave del modelo, y lo que Holded no sabe hacer:
            Pendiente de cobro = cobrado TEORICO acumulado - cobrado REAL

        No es "total de la factura menos lo cobrado". De un renting a 36 meses
        solo es exigible hoy la parte de cuotas ya vencidas segun el calendario
        de Eli; el resto todavia no es caja de este mes.
        """
        v = self.ventas.copy()
        if v.empty:
            return v

        # Alcance: el calendario de Eli arranca en un mes concreto (enero 2025).
        # Las facturas anteriores no tienen cuotas cargadas, asi que su "teorico
        # acumulado" saldria a cero y generaria falsos anticipos de millones.
        # Se excluyen: a esa altura o estan cobradas o se cedieron al banco.
        if not self.cal.empty:
            ini = self.cfg["cobros"].get("desde_mes", "auto")
            if ini == "auto":
                ini = str(self.cal["mes"].min())
            self.mes_inicio = ini
            antes = len(v)
            v = v[v.apply(lambda r: _ejercicio(r["num"], r["fecha"]) >= ini[:4], axis=1)]
            self.fuera_de_alcance = antes - len(v)
        else:
            self.mes_inicio, self.fuera_de_alcance = None, 0

        cal = self.cal.copy()
        cal["k"] = cal["factura"].map(norm)
        por_fac_mes = cal.groupby(["k", "mes"])["importe"].sum().to_dict()
        acum_hasta = cal[cal["mes"] <= self.mes].groupby("k")["importe"].sum().to_dict()
        # "estar en la hoja de Eli" != "tener cuotas". Un abono o una venta al
        # contado figuran en la hoja con el calendario vacio: son 100% exigibles.
        en_cal = self.cal.attrs.get("facturas_en_hoja") or set(cal["k"])

        v["k"] = v["num"].map(norm)
        v["en_calendario"] = v["k"].isin(en_cal)

        def teorico_hoy(r):
            acum = acum_hasta.get(r["k"], 0.0)
            if abs(acum) > 0.005:
                return acum                    # calendario de cuotas de Eli
            return r["total"]                  # sin calendario: exigible integra

        v["teorico_hoy"] = v.apply(teorico_hoy, axis=1)
        v["pendiente_cobro"] = v["teorico_hoy"] - v["liquidado"]
        v["cuota_mes"] = v["k"].map(lambda k: por_fac_mes.get((k, self.mes), 0.0))
        v["retraso"] = (v["pendiente_cobro"] - v["cuota_mes"]).clip(lower=0)

        # --- rentings financiados -------------------------------------------
        # Una factura de renting se cede al banco y entra integra en caja unos
        # meses despues de emitirse; el calendario de Eli solo recoge la cuota
        # que el cliente paga. Si no se modela, el forecast a 2-3 meses se queda
        # corto justo en la partida mas grande.
        rf = self.cfg["cobros"].get("rentings_financiados") or {}
        activo = rf.get("activo", False)
        desfase = int(rf.get("desfase_meses", 2))
        cuentas_rent = {norm(c) for c in (rf.get("cuentas_renting") or [])}
        v["es_renting"] = v["cuenta"].map(
            lambda c: any(p in norm(c) for p in cuentas_rent)) if cuentas_rent else False

        for i, m in enumerate(self.meses):
            col = f"teorico_{m}"
            if i == 0:
                v[col] = v["pendiente_cobro"]
                continue

            base = v["k"].map(lambda k, m=m: por_fac_mes.get((k, m), 0.0))
            if activo:
                # OJO: en el Excel las 4 columnas de meses futuros apuntan todas
                # a $J$1, asi que las mismas facturas de renting de junio se
                # cuentan en agosto, septiembre, octubre Y noviembre. Aqui cada
                # factura cae solo en su mes: mes_emision + desfase.
                cede = v.apply(
                    lambda r, m=m: r["total"] if (
                        r["es_renting"] and r.get("mes_factura")
                        and suma_meses(str(r["mes_factura"]), desfase) == m) else 0.0,
                    axis=1)
                v[col] = base.where(~v["es_renting"], 0.0) + cede
            else:
                v[col] = base

        # certidumbre 1 seguro / 2 posible / 3 retrasado
        def clasif(r):
            if r["retraso"] > 0.01:
                return 3
            if r["en_calendario"]:
                return 1
            return 2
        v["certidumbre"] = v.apply(clasif, axis=1)

        excl = {norm(c) for c in self.cfg["cobros"].get("excluir_clientes") or []}
        if excl:
            v = v[~v["cliente"].map(norm).isin(excl)]

        return v

    def cobros_por_cliente(self) -> pd.DataFrame:
        v = self.cobros_por_factura()
        if v.empty:
            return pd.DataFrame()
        cols = {"total": "sum", "liquidado": "sum", "pendiente_cobro": "sum",
                "cuota_mes": "sum", "retraso": "sum"}
        cols.update({f"teorico_{m}": "sum" for m in self.meses})
        act = v[(v["pendiente_cobro"].abs() > 0.01) |
                (v[[f"teorico_{m}" for m in self.meses[1:]]].abs().sum(axis=1) > 0.01)]
        g = act.groupby("cliente").agg(cols).reset_index()
        return g.sort_values("pendiente_cobro", ascending=False)

    def rentings_sin_factura(self) -> pd.DataFrame:
        """
        Cuotas del calendario de Eli que todavia no tienen factura en Holded.
        Existiran: son rentings contratados. Es el 'Ajustes Positivos (Rentings)'.
        """
        if not self.cfg["cobros"]["proyectar_rentings_sin_factura"] or self.cal.empty:
            return pd.DataFrame(columns=["cliente", "mes", "importe"])

        emitidas = (set(self.ventas["num"].map(norm))
                    if "num" in self.ventas.columns and not self.ventas.empty else set())
        cal = self.cal.copy()
        cal["k"] = cal["factura"].map(norm)
        futuro = cal[(~cal["k"].isin(emitidas)) & (cal["mes"].isin(self.meses))]
        if futuro.empty:
            return pd.DataFrame(columns=["cliente", "mes", "importe"])
        return (futuro.groupby(["cliente", "mes"])["importe"].sum()
                .reset_index().sort_values("importe", ascending=False))

    # =======================================================================
    #  PAGOS
    # =======================================================================
    def pagos_por_proveedor(self) -> pd.DataFrame:
        """
        Replica el SUMIFS del Excel: el forecast del mes X recoge TODO lo
        pendiente con vencimiento <= fin de X. Asi los vencidos se arrastran
        al mes en curso en lugar de perderse.
        """
        c = self.compras.copy()
        if c.empty or "pendiente" not in c.columns:
            return pd.DataFrame()
        c = c[c["pendiente"].abs() > 0.01]
        if c.empty:
            return pd.DataFrame()

        arrastrar = self.cfg["forecast"]["arrastrar_vencidos"]
        filas = []
        for prov, g in c.groupby("proveedor"):
            fila = {"proveedor": prov, "pendiente_total": g["pendiente"].sum()}
            acum = 0.0
            for m in self.meses:
                if arrastrar:
                    hasta = g[(g["mes_venc"].notna()) & (g["mes_venc"] <= m)]["pendiente"].sum()
                    fila[f"pago_{m}"] = hasta - acum
                    acum = hasta
                else:
                    fila[f"pago_{m}"] = g[g["mes_venc"] == m]["pendiente"].sum()
            fila["vencido"] = g[(g["mes_venc"].notna()) &
                                (g["mes_venc"] < self.mes)]["pendiente"].sum()
            fila["tipologia"] = g["tipologia"].mode().iat[0] if not g["tipologia"].mode().empty else ""
            filas.append(fila)

        df = pd.DataFrame(filas)
        df["certidumbre"] = df["vencido"].map(lambda x: 6 if x > 0.01 else 4)
        return df.sort_values("pendiente_total", ascending=False)

    def detalle_pagos(self) -> pd.DataFrame:
        """Facturas de compra pendientes, una por linea, para el desplegable."""
        c = self.compras.copy()
        if c.empty or "pendiente" not in c.columns:
            return pd.DataFrame()
        c = c[c["pendiente"].abs() > 0.01].copy()
        if c.empty:
            return c
        c["vencido"] = c["mes_venc"].map(
            lambda m: bool(m) and str(m) < self.mes)
        c["mes_forecast"] = c["mes_venc"].map(
            lambda m: self.mes if (m and str(m) <= self.mes) else (
                str(m) if str(m) in self.meses else "posterior"))
        return c.sort_values(["proveedor", "vencimiento"])

    # -----------------------------------------------------------------------
    def salarios_mes(self) -> tuple[float, list]:
        s = self.cfg["salarios"]
        det = [{"concepto": "Nomina neta", "importe": -s["nomina_neta"]},
               {"concepto": "Otros personal", "importe": -s["otros_personal"]}]
        for x in s.get("servicios_con_iva") or []:
            det.append({"concepto": x["concepto"] + " (IVA inc.)",
                        "importe": -x["base"] * (1 + s["iva"])})
        return sum(d["importe"] for d in det), det

    def cuotas_sl_mes(self) -> tuple[float, list]:
        ops = self.cfg["cuotas_sl"].get("operaciones") or []
        if ops:
            det = [{"concepto": f"{o['operacion']} - {o['proveedor']}",
                    "importe": -o["importe"]} for o in ops]
        else:
            # deducir de Holded: ultima cuota conocida por proveedor con Tipologia S&L
            sl = self.compras[self.compras["tipologia"].map(norm) == "S&L"]
            det = [{"concepto": p, "importe": -g.sort_values("fecha")["total"].iat[-1]}
                   for p, g in sl.groupby("proveedor")] if not sl.empty else []
        return sum(d["importe"] for d in det), det

    def recurrentes_proyectados(self) -> pd.DataFrame:
        """
        Para cada proveedor recurrente y cada mes de forecast: si NO hay factura
        en Holded con vencimiento en ese mes, se proyecta el importe base.
        Si SI la hay, se deja a 0 (ya esta contada en pagos_por_proveedor).
        """
        cfg = self.cfg["recurrentes"]
        c = self.compras.copy()
        if c.empty or "proveedor" not in c.columns:
            return pd.DataFrame(columns=["proveedor", "grupo", "mes", "base_mensual",
                                         "frecuencia", "facturado_en_holded", "proyectado"])
        c["_p"] = c["proveedor"].map(norm)

        ventana = [suma_meses(self.mes, -i) for i in range(1, cfg["ventana_meses"] + 1)]
        filas = []
        for r in cfg["proveedores"]:
            pat = norm(r["patron"])
            sub = c[c["_p"].str.contains(pat, regex=False, na=False)]
            if sub.empty:
                continue
            hist = sub[sub["mes_venc"].isin(ventana)]
            por_mes = hist.groupby("mes_venc")["total"].sum()
            activos = por_mes[por_mes.abs() > 0.01]
            if activos.empty:
                continue

            metodo = cfg["metodo_base"]
            if metodo == "media":
                base = por_mes.reindex(ventana).fillna(0).mean()
            elif metodo == "media_movil_3":
                base = por_mes.reindex(ventana).fillna(0).iloc[:3].mean()
            else:                                    # mediana de meses con gasto
                base = float(activos.median())

            # frecuencia: cuantos de los ultimos 12 meses tuvieron gasto
            frec = len(activos) / len(ventana)

            for m in self.meses:
                ya = sub[sub["mes_venc"] == m]["total"].sum()
                proy = 0.0 if abs(ya) > 0.01 else base * (1 if frec >= 0.5 else frec)
                filas.append({
                    "proveedor": r["etiqueta"], "grupo": r["grupo"], "mes": m,
                    "base_mensual": base, "frecuencia": frec,
                    "facturado_en_holded": ya, "proyectado": -proy,
                })
        return pd.DataFrame(filas)

    # =======================================================================
    #  FORECAST CONSOLIDADO
    # =======================================================================
    def forecast(self) -> dict:
        cli = self.cobros_por_cliente()
        rent = self.rentings_sin_factura()
        prov = self.pagos_por_proveedor()
        recu = self.recurrentes_proyectados()
        sal, sal_det = self.salarios_mes()
        sl, sl_det = self.cuotas_sl_mes()

        cob_cfg = self.cfg["cobros"]
        sin_fact = sum(x["unidades"] * x["precio"] * (1 + x["iva"])
                       for x in cob_cfg.get("sin_facturar") or [])
        aj_neg = sum(x["importe"] for x in cob_cfg.get("ajustes_negativos") or [])
        aj_pos = sum(x["importe"] for x in cob_cfg.get("ajustes_positivos") or [])

        out = {}
        for i, m in enumerate(self.meses):
            c_cli = float(cli[f"teorico_{m}"].sum()) if not cli.empty else 0.0
            c_ren = float(rent[rent["mes"] == m]["importe"].sum()) if not rent.empty else 0.0
            # las ventas sin facturar y los ajustes solo aplican al mes en curso
            c_sf = sin_fact if i == 0 else 0.0
            c_aj = (aj_neg + aj_pos) if i == 0 else 0.0

            p_prov = float(prov[f"pago_{m}"].sum()) if not prov.empty else 0.0
            p_recu = float(recu[recu["mes"] == m]["proyectado"].sum()) if not recu.empty else 0.0
            p_otros = -self.cfg["otros_pagos_fijos"]

            cash_in = c_cli + c_ren + c_sf + c_aj
            cash_out = -abs(p_prov) + p_recu + sal + sl + p_otros

            out[m] = {
                "mes": m, "etiqueta": nombre_mes(m),
                "cobro_clientes": c_cli,
                "rentings_sin_factura": c_ren,
                "ventas_sin_facturar": c_sf,
                "ajustes_cobros": c_aj,
                "cash_in": cash_in,
                "pago_proveedores": -abs(p_prov),
                "recurrentes_proyectados": p_recu,
                "salarios": sal,
                "cuotas_sl": sl,
                "otros_fijos": p_otros,
                "cash_out": cash_out,
                "fcf": cash_in + cash_out,
            }

        # posicion bancaria y proyeccion de saldo
        b = self.d["bancos"]
        saldo_cta = float(b[b["tipo"] == "cuenta"]["saldo"].sum()) if not b.empty else 0.0
        disp_pol = float(b[b["tipo"] == "poliza"]["saldo"].sum()) if not b.empty else 0.0

        acum = saldo_cta
        for m in self.meses:
            acum += out[m]["fcf"]
            out[m]["saldo_proyectado"] = acum
            out[m]["saldo_proyectado_con_polizas"] = acum + disp_pol

        return {
            "meses": self.meses, "lineas": out,
            "saldo_actual": saldo_cta, "polizas_disponible": disp_pol,
            "detalle": {"salarios": sal_det, "cuotas_sl": sl_det},
            "clientes": cli, "rentings": rent, "proveedores": prov, "recurrentes": recu,
            "detalle_cobros": self.cobros_por_factura(),
            "detalle_pagos": self.detalle_pagos(),
        }

    # =======================================================================
    #  CUADRE DE CAJA
    # =======================================================================
    def cuadre_proyeccion(self, fc: dict) -> list[dict]:
        """
        La comprobacion que pide cualquier controller sobre un forecast:
            saldo inicial + cobros - pagos == saldo final
        Se calcula de forma independiente y se compara, en lugar de arrastrar
        el saldo: si algun mes no cuadrase, seria un error del motor.
        """
        filas, saldo = [], fc["saldo_actual"]
        for m in fc["meses"]:
            L = fc["lineas"][m]
            final_esperado = saldo + L["cash_in"] + L["cash_out"]
            final_motor = L["saldo_proyectado"]
            dif = final_motor - final_esperado
            filas.append({
                "mes": m, "etiqueta": L["etiqueta"],
                "saldo_inicial": saldo,
                "cash_in": L["cash_in"],
                "cash_out": L["cash_out"],
                "fcf": L["fcf"],
                "saldo_final": final_motor,
                "diferencia": dif,
                "cuadra": abs(dif) < 0.01,
            })
            saldo = final_motor
        return filas

    def cuadre(self, mes: str | None = None) -> dict:
        """
        Check del controller:
            cobros del mes - pagos del mes  ==  saldo final - saldo inicial

        Lo que no cuadre son movimientos que no pasan por factura: nominas,
        impuestos, comisiones, disposiciones de poliza, prestamos, traspasos.
        """
        mes = mes or self.mes
        v, c = self.ventas, self.compras

        def liquidado_del_mes(df):
            if df.empty or "fecha_liq" not in df.columns:
                return 0.0
            return float(df[df["fecha_liq"].map(mes_de) == mes]["liquidado"].sum())

        cobros = liquidado_del_mes(v)
        pagos = liquidado_del_mes(c)
        flujo_facturas = cobros - pagos

        mv = self.d.get("movimientos")
        if mv is not None and not mv.empty:
            mv = mv.copy()
            mv["mes"] = mv["fecha"].map(mes_de)
            variacion = float(mv[mv["mes"] == mes]["importe"].sum())
            fuente = "movimientos de tesoreria de Holded"
            por_cuenta = (mv[mv["mes"] == mes].groupby("cuenta")["importe"].sum()
                          .reset_index().to_dict("records"))
        else:
            variacion = None
            fuente = "sin movimientos bancarios (extraccion via Excel)"
            por_cuenta = []

        dif = None if variacion is None else flujo_facturas - variacion
        tol = self.cfg["cuadre"]["tolerancia_eur"]

        # Conciliacion linea a linea: que movimientos del banco NO se
        # corresponden con el cobro o el pago de una factura. Esos son la
        # explicacion de la diferencia, y darlos por su nombre es la diferencia
        # entre "no cuadra por 179.550" y "no cuadra: son las nominas".
        sin_conciliar, resumen = [], []
        if mv is not None and not mv.empty:
            liq = []
            for df, signo in ((v, 1), (c, -1)):
                if df.empty or "fecha_liq" not in df.columns:
                    continue
                sub = df[df["fecha_liq"].map(mes_de) == mes]
                for _, r in sub.iterrows():
                    if abs(r["liquidado"]) > 0.01:
                        liq.append((abs(r["liquidado"]), r["fecha_liq"]))
            usados = set()
            for _, r in mv[mv["mes"] == mes].iterrows():
                imp = abs(r["importe"])
                casa = None
                for i, (m_imp, m_f) in enumerate(liq):
                    if i in usados or abs(m_imp - imp) > 0.5:
                        continue
                    if r["fecha"] and m_f and abs((r["fecha"] - m_f).days) <= 5:
                        casa = i
                        break
                if casa is not None:
                    usados.add(casa)
                else:
                    sin_conciliar.append({
                        "fecha": r["fecha"], "cuenta": r["cuenta"],
                        "concepto": r["concepto"] or "(sin concepto)",
                        "importe": float(r["importe"]),
                    })
            if sin_conciliar:
                sc = pd.DataFrame(sin_conciliar)
                resumen = (sc.assign(g=sc["concepto"].str.slice(0, 40))
                           .groupby("g")["importe"].sum()
                           .reset_index().sort_values("importe", key=abs, ascending=False)
                           .rename(columns={"g": "concepto"}).to_dict("records"))

        explicado = sum(x["importe"] for x in sin_conciliar)

        return {
            "mes": mes, "etiqueta": nombre_mes(mes),
            "cobros_ejecutados": cobros,
            "pagos_ejecutados": pagos,
            "flujo_por_facturas": flujo_facturas,
            "variacion_bancaria": variacion,
            "diferencia": dif,
            "cuadra": None if dif is None else abs(dif) <= tol,
            "tolerancia": tol,
            "fuente": fuente,
            "por_cuenta": por_cuenta,
            "sin_conciliar": sin_conciliar,
            "resumen_sin_conciliar": resumen,
            "importe_sin_conciliar": explicado,
            "residuo": (None if dif is None else dif + explicado),
            "explicacion": (
                "La diferencia recoge los movimientos que no pasan por factura: "
                "nominas y seguros sociales, impuestos, comisiones bancarias, "
                "disposiciones y amortizaciones de poliza, prestamos y traspasos "
                "entre cuentas propias."
            ),
        }

    # =======================================================================
    #  ALERTAS
    # =======================================================================
    def alertas(self, fc: dict) -> list[dict]:
        a = []
        L = fc["lineas"]

        for m in fc["meses"]:
            if L[m]["saldo_proyectado"] < 0:
                a.append({"nivel": "critico",
                          "texto": f"Saldo proyectado negativo en {L[m]['etiqueta']}: "
                                   f"{L[m]['saldo_proyectado']:,.0f} EUR sin tirar de polizas."})
            elif L[m]["saldo_proyectado"] < 100_000:
                a.append({"nivel": "aviso",
                          "texto": f"Colchon ajustado en {L[m]['etiqueta']}: "
                                   f"{L[m]['saldo_proyectado']:,.0f} EUR."})

        cli = fc["clientes"]
        if not cli.empty:
            top = cli.nlargest(5, "retraso")
            for _, r in top.iterrows():
                if r["retraso"] > 20_000:
                    a.append({"nivel": "aviso",
                              "texto": f"{r['cliente']}: {r['retraso']:,.0f} EUR de retraso "
                                       f"sobre el calendario de cobro."})

        prov = fc["proveedores"]
        if not prov.empty:
            venc = prov["vencido"].sum()
            if venc > 50_000:
                n = int((prov["vencido"] > 0.01).sum())
                a.append({"nivel": "aviso",
                          "texto": f"{venc:,.0f} EUR vencidos y sin pagar en {n} proveedores."})

        conc = fc["clientes"]
        if not conc.empty and conc["pendiente_cobro"].sum() > 0:
            peso = conc.iloc[0]["pendiente_cobro"] / conc["pendiente_cobro"].sum()
            if peso > 0.20:
                a.append({"nivel": "aviso",
                          "texto": f"Concentracion de riesgo: {conc.iloc[0]['cliente']} "
                                   f"es el {peso:.0%} del pendiente de cobro."})
        return a
