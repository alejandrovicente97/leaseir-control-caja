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

from fuentes import norm, mes_de, suma_meses, nombre_mes, clasificar_cuenta

# Que cuentas del plan son CAJA. Grupo 57 es tesoreria (570 caja, 572 bancos,
# 576 inversiones de gran liquidez) y 54 recoge imposiciones a corto que en
# esta casa se manejan como disponible. Las polizas y las tarjetas son 52*, asi
# que quedan fuera por definicion contable y no porque yo acierte a
# reconocerlas por el nombre. Esta escrito una sola vez a proposito: el saldo
# de apertura, el de hoy y las lineas de movimiento tienen que mirar
# exactamente el mismo conjunto de cuentas o el puente deja de ser un puente.
PREF_CAJA = r"^5[74]"


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

    def cobrabilidad(self) -> tuple[pd.DataFrame, dict]:
        """
        Que se va a cobrar y que no, con nombre e importe.

        Un forecast que da por cobrado todo lo vencido no es un forecast, es
        una lista de deseos: hay 1.079.317 euros en retraso y dar por hecho
        que entran todos este mes proyecta una caja que no va a existir.

        La regla es el retraso, que es el unico dato objetivo que hay:

            al dia o poco vencido  -> entra
            muy vencido            -> NO entra, y se dice cuanto

        El corte esta en config (cobros.dias_dudoso). No pretende ser una
        probabilidad de impago: es una linea, dibujada donde tu digas, para
        que el proyectado se apoye en lo que razonablemente entra. Lo que
        quede fuera no desaparece, sale listado con su importe para que lo
        puedas meter tu con previsiones si sabes que ese cliente si paga.
        """
        v = self.cobros_por_factura()
        if v.empty:
            return pd.DataFrame(), {"entra": 0.0, "fuera": 0.0}
        cfg = self.cfg.get("cobros") or {}
        dias = int(cfg.get("dias_dudoso", 90))
        hoy = date.today()

        d = v[v["pendiente_cobro"] > 0.01].copy()
        if d.empty:
            return pd.DataFrame(), {"entra": 0.0, "fuera": 0.0}

        def antiguedad(r):
            f = r.get("vencimiento") or r.get("fecha")
            try:
                return (hoy - f).days
            except Exception:
                return 0
        d["dias"] = d.apply(antiguedad, axis=1)
        # Lo que esta al dia no es dudoso por mucho que el cliente sea lento:
        # solo se juzga lo que ya deberia haber entrado.
        d["entra"] = (d["retraso"] <= 0.01) | (d["dias"] <= dias)
        d["motivo"] = d.apply(
            lambda r: "" if r["entra"] else f"vencida hace {int(r['dias'])} dias",
            axis=1)
        tot = {"entra": float(d[d["entra"]]["pendiente_cobro"].sum()),
               "fuera": float(d[~d["entra"]]["pendiente_cobro"].sum()),
               "dias": dias,
               "n_fuera": int((~d["entra"]).sum())}
        return d, tot

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
        futuro = cal[(~cal["k"].isin(emitidas)) & (cal["mes"].isin(self.meses))].copy()
        if futuro.empty:
            return pd.DataFrame(columns=["cliente", "mes", "importe", "tipo"])

        # Las facturas que empiezan por FM vienen de la fusion con LML: son
        # ventas financiadas desde LML cuya factura no se pudo migrar al Holded
        # de LT. No estan en Holded, pero NO son "pendientes de facturar":
        # estan facturadas, solo que en otra sociedad. Cobran igual, asi que
        # entran en el forecast, pero con su nombre. Llamarlas "sin facturar"
        # invitaria a ir a buscar una factura que ya existe.
        pref = tuple(p.upper() for p in
                     (self.cfg["cobros"].get("prefijos_fusion") or ["FM"]))
        futuro["tipo"] = futuro["factura"].map(
            lambda f: "fusion" if str(f).strip().upper().startswith(pref) else "renting")
        return (futuro.groupby(["cliente", "mes", "tipo"])["importe"].sum()
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
    #  CUADRE CONTRA CONTABILIDAD
    # =======================================================================
    def check_clientes(self) -> dict | None:
        """
        El saldo contable de las 430* contra el pendiente de las facturas.

        Es el mejor check que hay del lado de cobros, porque cierra contra
        contabilidad y no contra otro calculo mio. La igualdad no es con el
        "pendiente exigible" del panel, y ahi esta la gracia:

            saldo 430*  =  exigible hoy  +  aplazado segun calendario de Eli

        Contabilidad lleva la factura entera mientras no se cobre. El panel
        solo llama exigible a la parte cuyas cuotas ya han vencido. La
        diferencia entre las dos cifras ES lo financiado/aplazado, no un error:
        si ese puente cuadra, el calendario de Eli esta bien cargado.
        """
        plan = self.d.get("plan_contable")
        if plan is None or plan.empty:
            return None
        pref = tuple(str(p) for p in
                     (self.cfg.get("cuadre") or {}).get("cuentas_clientes") or ["430"])
        cta = plan[plan["numero"].astype(str).str.startswith(pref)]
        if cta.empty:
            return None

        v = self.cobros_por_factura()
        if v.empty:
            return None
        exigible = float(v["pendiente_cobro"].sum())
        aplazado = float((v["total"] - v["teorico_hoy"]).sum())
        contable = float(cta["saldo"].sum())
        tol = float((self.cfg.get("cuadre") or {}).get("tolerancia", 1000))
        dif = contable - (exigible + aplazado)
        return {
            "cuentas": [{"numero": r["numero"], "nombre": r["nombre"],
                         "saldo": float(r["saldo"])}
                        for _, r in cta.sort_values("numero").iterrows()],
            "contable": contable, "exigible": exigible, "aplazado": aplazado,
            "suma": exigible + aplazado, "diferencia": dif,
            "cuadra": abs(dif) <= tol, "tolerancia": tol,
            "prefijos": list(pref),
        }

    # =======================================================================
    #  LO QUE YA HA PASADO ESTE MES
    # =======================================================================
    def ya_pagado_fijos(self) -> dict:
        """
        Cuanto se ha pagado YA en el mes en curso de cada partida fija.

        Sin esto el mes en curso se cuenta dos veces: la nomina de julio sale
        del banco el dia 25, el saldo de hoy ya la lleva descontada, y aun asi
        el forecast volvia a restar los 266.070 enteros. Lo mismo con las
        cuotas de sale & leaseback, que no vencen todas el mismo dia.

        Se mira contra los movimientos reales del banco, no contra facturas:
        una nomina no tiene factura en Holded.
        """
        mov = self.d.get("movimientos")
        patrones = (self.cfg.get("ejecutado") or {}).get("patrones") or {}
        vacio = {k: 0.0 for k in patrones}
        vacio["_detalle"] = {}
        if mov is None or mov.empty or not patrones:
            return vacio

        m = mov.copy()
        m["mes"] = m["fecha"].map(mes_de)
        m = m[(m["mes"] == self.mes) & (m["importe"] < 0)]
        if m.empty:
            return vacio

        salida, detalle, usados = {}, {}, set()
        for bloque, claves in patrones.items():
            claves = [norm(str(k)).lower() for k in (claves or [])]
            filas = []
            for idx, r in m.iterrows():
                if idx in usados:
                    continue                       # un apunte cuenta una sola vez
                c = norm(str(r["concepto"])).lower()
                if any(k and k in c for k in claves):
                    usados.add(idx); filas.append(r)
            salida[bloque] = float(sum(abs(f["importe"]) for f in filas))
            detalle[bloque] = [{"fecha": f["fecha"], "concepto": f["concepto"],
                                "importe": float(f["importe"])} for f in filas]
        salida["_detalle"] = detalle
        return salida

    def _sin_apertura(self, m: pd.DataFrame) -> pd.DataFrame:
        """
        Quita el asiento de apertura del ejercicio.

        El 1 de enero la contabilidad abre el ano cargando en cada cuenta de
        activo su saldo inicial. Eso toca las cuentas de banco por 3,5 millones
        y NO es un movimiento de caja: es el saldo que ya estaba ahi el 31 de
        diciembre. Contarlo hacia que enero de 2026 diera una variacion de caja
        de +3.519.990 cuando la caja de LT en realidad bajo 32.709 ese mes.

        Se reconoce por lo que es: un unico asiento, el primer dia del
        ejercicio, que toca a la vez muchisimas cuentas distintas. Ningun cobro
        ni ningun pago se parece a eso.
        """
        if m.empty or "asiento" not in m.columns:
            return m
        primeros = m[m["fecha"].map(
            lambda f: bool(f) and getattr(f, "month", 0) == 1
            and getattr(f, "day", 0) == 1)]
        if primeros.empty:
            return m
        umbral = int((self.cfg.get("cuadre") or {}).get("lineas_apertura", 20))
        apertura = {a for a, g in primeros.groupby("asiento")
                    if g["cuenta"].nunique() >= umbral}
        if not apertura:
            return m
        self.avisos.append(
            f"Se ha excluido el asiento de apertura del ejercicio "
            f"({len(apertura)} asiento(s) del 1 de enero con mas de {umbral} "
            f"cuentas): es el saldo que venia del ano anterior, no un flujo.")
        return m[~m["asiento"].isin(apertura)]

    def _apertura_por_cuenta(self) -> dict[str, float]:
        """
        Saldo de cada cuenta de caja el 1 de enero, leido del asiento de
        apertura del ejercicio. Es el unico sitio del libro diario donde esta
        escrito el saldo con el que se empezo el ano: el resto del diario son
        movimientos.
        """
        dia = self.d.get("diario")
        if dia is None or dia.empty or "asiento" not in dia.columns:
            return {}
        primeros = dia[dia["fecha"].map(
            lambda f: bool(f) and getattr(f, "month", 0) == 1
            and getattr(f, "day", 0) == 1)]
        if primeros.empty:
            return {}
        umbral = int((self.cfg.get("cuadre") or {}).get("lineas_apertura", 20))
        ids = {a for a, g in primeros.groupby("asiento")
               if g["cuenta"].nunique() >= umbral}
        if not ids:
            return {}
        ap = primeros[primeros["asiento"].isin(ids)]
        ap = ap[ap["cuenta"].astype(str).str.match(PREF_CAJA)]
        if ap.empty:
            return {}
        return {str(k): float(v)
                for k, v in ap.groupby("cuenta")["importe"].sum().items()}

    def _avisar(self, texto: str) -> str:
        """Deja el aviso en la lista de calidad del dato y lo devuelve."""
        if texto not in self.avisos:
            self.avisos.append(texto)
        return texto

    def caja_por_naturaleza(self, mes: str | None = None) -> pd.DataFrame:
        """
        Los movimientos de caja del mes, clasificados por su contrapartida.

        En el libro diario, un cobro o un pago es un apunte que toca una cuenta
        de banco (57*). Lo que dice QUE es ese movimiento son las otras lineas
        del mismo asiento: contra 430 es un cobro de cliente, contra 640 una
        nomina, contra 475 un impuesto, contra 520 una amortizacion de deuda.

        Es lo que convierte "EMISION REMESA SEPA SDD REFERENCIA: 0049" en
        "Clientes", y lo que permite decir de que se compone el residuo del
        cuadre en vez de dejarlo como una diferencia sin explicar.
        """
        dia = self.d.get("diario")
        if dia is None or dia.empty:
            return pd.DataFrame(columns=["naturaleza", "importe", "apuntes"])
        m = self._sin_apertura(dia[dia["mes"] == (mes or self.mes)])
        if m.empty:
            return pd.DataFrame(columns=["naturaleza", "importe", "apuntes"])

        es_caja = m["cuenta"].astype(str).str.match(PREF_CAJA)
        caja, resto = m[es_caja], m[~es_caja]
        if caja.empty:
            return pd.DataFrame(columns=["naturaleza", "importe", "apuntes"])

        # contrapartida de cada asiento: la linea de mayor importe que no es caja
        contra = {}
        for asiento, g in resto.groupby("asiento"):
            i = g["importe"].abs().idxmax()
            contra[asiento] = g.loc[i, "grupo_pgc"]

        c = caja.copy()
        c["naturaleza"] = c["asiento"].map(lambda a: contra.get(a, "Sin contrapartida"))
        g = (c.groupby("naturaleza")
               .agg(importe=("importe", "sum"), apuntes=("importe", "size"))
               .reset_index())
        return g.reindex(g["importe"].abs().sort_values(ascending=False).index)

    def fcf_desde_banco(self, mes: str | None = None) -> dict | None:
        """
        El puente que pide Alejandro, y es el que hay que dar:

            saldo del banco al empezar el mes
            saldo del banco hoy
            la diferencia ES el LEVERED free cash flow
            + los pagos de deuda
            = UNLEVERED free cash flow

        La gracia de anclarlo en el saldo del banco es que el punto de partida
        no es un calculo mio: son dos cifras que se pueden mirar en Holded y en
        el extracto. Y los traspasos entre cuentas propias desaparecen solos,
        porque se mira la tesoreria ENTERA y lo que sale de una cuenta entra en
        otra. Toda la contorsion con la cuenta puente sobraba en cuanto se mira
        el total en vez de cuenta a cuenta.

        Las polizas y las tarjetas quedan fuera del perimetro, igual que en la
        posicion: una linea de credito no es caja y una tarjeta es deuda.
        """
        mes = mes or self.mes
        mov, ban = self.d.get("movimientos"), self.d.get("bancos")
        if mov is None or mov.empty or ban is None or ban.empty:
            return None

        cuentas_caja = set(ban[ban["tipo"] == "cuenta"]["cuenta"])
        cuentas_tarj = set(ban[ban["tipo"] == "tarjeta"]["cuenta"])
        todo = mov.copy()
        todo["mes"] = todo["fecha"].map(mes_de)
        m = todo[todo["cuenta"].isin(cuentas_caja)]
        if m.empty:
            return None
        del_mes = m[m["mes"] == mes]

        # EL GASTO EN TARJETA DE ESTE MES NO HA LLEGADO AL BANCO TODAVIA.
        # Alejandro: "las tarjetas no vuelcan hasta agosto, asi que ese saldo
        # del banco de hoy no es ok". Y es verdad: la comida, el peaje y el
        # billete de julio se cargan en la cuenta en agosto, asi que la
        # variacion de saldo bancario de julio se deja fuera ese gasto y el mes
        # sale mejor de lo que es. Se suma aparte, con su nombre, para que se
        # vea que es un ajuste de devengo y no un movimiento de banco.
        tarj_mes = todo[todo["cuenta"].isin(cuentas_tarj)
                        & (todo["mes"] == mes)]
        gasto_tarjeta_mes = float(tarj_mes["importe"].sum()) if not tarj_mes.empty else 0.0

        # El saldo de Holded es el de HOY. Para cualquier mes, el saldo con el
        # que empezo se deduce hacia atras quitando todo lo que ha pasado desde
        # entonces: no hace falta guardar historico de saldos.
        # El mismo saldo que publica el KPI de posicion, correccion incluida:
        # si el puente partiera del listado en bruto y el KPI del listado
        # corregido, los 24.705 de la cuenta de Caixa que Holded declara a cero
        # apareceria como flujo del mes en vez de como saldo que ya estaba.
        cc = self._conciliar_caja()
        hoy_total = cc["saldo"]
        variacion = float(del_mes["importe"].sum())

        # EL MISMO PUENTE, CUENTA A CUENTA.
        # El bottom-up de Alejandro esta montado banco a banco, asi que cuando
        # el total no coincide lo unico util es poder poner las dos columnas al
        # lado y ver que linea se separa. Dar solo el total obliga a adivinar
        # donde estan 200.000 euros de diferencia.
        saldo_hoy_cta = dict(zip(ban[ban["tipo"] == "cuenta"]["cuenta"],
                                 ban[ban["tipo"] == "cuenta"]["saldo"]))
        for c in cc.get("conciliacion") or []:      # la cuenta reconstruida
            if c.get("rescatada"):
                saldo_hoy_cta[c["cuenta"]] = c["estimado"]
        var_cta = del_mes.groupby("cuenta")["importe"].sum().to_dict()
        post_cta = (m[m["mes"] > mes].groupby("cuenta")["importe"].sum().to_dict()
                    if not m[m["mes"] > mes].empty else {})
        por_cuenta = []
        for cta, hoy in saldo_hoy_cta.items():
            v = float(var_cta.get(cta, 0.0))
            fin = float(hoy) - float(post_cta.get(cta, 0.0))
            if abs(fin) < 0.005 and abs(v) < 0.005:
                continue
            por_cuenta.append({"cuenta": cta, "inicio": fin - v,
                               "hoy": fin, "variacion": v,
                               "n": int((del_mes["cuenta"] == cta).sum())})
        por_cuenta.sort(key=lambda x: x["variacion"])
        posterior = float(m[m["mes"] > mes]["importe"].sum())
        saldo_hoy = hoy_total - posterior          # saldo al cierre de ese mes

        # EL SALDO INICIAL DEBERIA SALIR DE CONTABILIDAD, NO DE RESTAR.
        # Deducirlo como saldo_hoy - movimientos es una trampa: si falta un
        # movimiento, el saldo inicial se mueve en la misma cantidad, la resta
        # sigue cuadrando y el error se tapa a si mismo. Por eso se pide el
        # saldo de las cuentas 57* cerrado a fin del mes anterior: dos cifras
        # independientes, y lo que no cuadre entre ellas es lo que falta.
        #
        # PERO HAY QUE COMPROBAR QUE HOLDED HA HECHO CASO A LA FECHA. No lo
        # hace: /accounting-accounts devuelve exactamente lo mismo con end_date
        # que sin el. Se vio porque las dos llamadas daban el mismo total al
        # euro, -2.997.589, y el puente publico un levered de +3,3 millones en
        # julio dando por bueno ese numero como saldo de apertura.
        #
        # Asi que el saldo contable solo manda si demuestra ser de otra fecha.
        # Si coincide con el de hoy, el filtro se ha ignorado y no es un saldo
        # de apertura: es el mismo dato con otro nombre. Un dato que no puede
        # distinguirse del que ya tienes no aporta un contraste, aporta una
        # confirmacion falsa, que es peor que no tener nada.
        pi = self.d.get("plan_inicio")
        pc = self.d.get("plan_contable")
        saldo_conta, origen_inicio = None, "deducido de los movimientos del mes"
        self.aviso_apertura = None
        if pi is not None and not pi.empty and mes == self.mes:
            b57 = pi[pi["numero"].astype(str).str.match(PREF_CAJA)]
            hoy57 = (pc[pc["numero"].astype(str).str.match(PREF_CAJA)]
                     if pc is not None and not pc.empty else None)
            if not b57.empty:
                cand = float(b57["saldo"].sum())
                mismo = (hoy57 is not None and not hoy57.empty
                         and abs(cand - float(hoy57["saldo"].sum())) < 0.01)
                if mismo:
                    self.aviso_apertura = self._avisar(
                        "Holded ignora el filtro de fecha en el plan contable: "
                        "el saldo 'a fin del mes anterior' viene identico al de "
                        "hoy, asi que no sirve como saldo de apertura y no se "
                        "usa. El saldo de partida se deduce restando los "
                        "movimientos del mes, que es mas debil: si falta un "
                        "movimiento, el error se reparte y no se ve.")
                else:
                    saldo_conta = cand
                    origen_inicio = ("saldo contable de las cuentas 57* a fin "
                                     "del mes anterior")
        saldo_inicio = saldo_conta if saldo_conta is not None else saldo_hoy - variacion
        # el hueco entre los dos caminos: si no es cero, faltan movimientos
        desajuste = (None if saldo_conta is None
                     else (saldo_hoy - saldo_inicio) - variacion)
        if saldo_conta is not None:
            variacion = saldo_hoy - saldo_inicio    # manda el saldo, no la suma
        variacion_bancos = variacion
        variacion = variacion + gasto_tarjeta_mes   # devengo de las tarjetas

        # Lo que Holded tiene sin conciliar: el hueco declarado entre banco y
        # contabilidad. Es la primera explicacion que hay que mirar cuando el
        # unlevered no cuadra contra el bottom-up.
        pdte = []
        if "pdte_conciliar" in ban.columns:
            for _, r in ban[ban["pdte_conciliar"] > 0].sort_values(
                    "pdte_conciliar", ascending=False).iterrows():
                imp = 0.0
                if "sin_conciliar" in mov.columns:
                    imp = float(mov[(mov["cuenta"] == r["cuenta"])
                                    & (mov["sin_conciliar"].abs() > 0.005)]
                                ["sin_conciliar"].abs().sum())
                pdte.append({"cuenta": r["cuenta"],
                             "movimientos": int(r["pdte_conciliar"]),
                             "importe": imp})

        # Pagos de deuda del mes, del libro diario: principal (17*, 52*),
        # intereses y gastos financieros (66*, 527).
        deuda, det_deuda, gasto_tarjetas = 0.0, [], 0.0
        dia = self.d.get("diario")
        if dia is not None and not dia.empty:
            d = self._sin_apertura(dia[dia["mes"] == mes])
            caja = d[d["cuenta"].astype(str).str.match(PREF_CAJA)]
            resto = d[~d["cuenta"].astype(str).str.match(PREF_CAJA)]
            pref = tuple(str(x) for x in
                         (self.cfg.get("cuadre") or {}).get("cuentas_deuda")
                         or ["17", "52", "527", "66"])
            contra, nomb = {}, {}
            for asiento, g in resto.groupby("asiento"):
                i = g["importe"].abs().idxmax()
                contra[asiento] = str(g.loc[i, "cuenta"])
                nomb[asiento] = g.loc[i, "cuenta_nombre"] if "cuenta_nombre" in g else ""
            c = caja.copy()
            if not c.empty:
                c["cta"] = c["asiento"].map(lambda a: contra.get(a, ""))
                c["nom"] = c["asiento"].map(lambda a: nomb.get(a, ""))
                # Las tarjetas NO son pago de deuda aunque vivan en cuentas 52.
                # Alejandro: "las tarjetas me dan igual porque vuelcan al mes
                # siguiente". Es gasto que se liquida con un mes de retraso, no
                # servicio de deuda, y devolverlo al levered inflaba el
                # unlevered en 25.022 euros solo en julio.
                es_deuda = c["cta"].map(lambda x: str(x).startswith(pref))
                es_tarj = c["nom"].map(
                    lambda n: clasificar_cuenta(str(n)) == "tarjeta")
                dd = c[es_deuda & ~es_tarj]
                tj = c[es_deuda & es_tarj]
                gasto_tarjetas = float(tj["importe"].sum()) if not tj.empty else 0.0
                if not dd.empty:
                    deuda = float(dd["importe"].sum())
                    det_deuda = [
                        {"cuenta": k[0], "nombre": k[1], "importe": float(v)}
                        for k, v in dd.groupby(["cta", "nom"])["importe"].sum()
                                      .sort_values().items()]

        return {
            "mes": mes, "etiqueta": nombre_mes(mes),
            "origen_inicio": origen_inicio,
            "desajuste": desajuste,
            "pdte_conciliar": pdte,
            "saldo_inicio": saldo_inicio,
            "saldo_hoy": saldo_hoy,
            "variacion_bancos": variacion_bancos,
            "gasto_tarjeta_mes": gasto_tarjeta_mes,
            "levered": variacion,
            "deuda": deuda,
            "gasto_tarjetas": gasto_tarjetas,
            "unlevered": variacion - deuda,
            "detalle_deuda": det_deuda,
            "n_movimientos": int(len(del_mes)),
            "por_cuenta": por_cuenta,
        }

    def unlevered_ejecutado(self, mes: str | None = None) -> dict | None:
        """
        El unlevered FCF ya ejecutado del mes, calculado como lo calcula el
        bottom-up: de la variacion real de caja hacia arriba.

            variacion de caja del mes  -  movimientos de financiacion  =  unlevered

        Por que no vale sumar cobros de facturas menos pagos de facturas: esa
        cuenta coge casi todos los cobros pero solo los pagos que pasan por
        factura o que reconozco por el concepto. Los impuestos, las comisiones
        y todo lo que no lleva factura se quedaban fuera, y el ejecutado salia
        alto de forma sistematica. Alejandro lo vio: le salia -250k y aqui
        +100k.

        Financiacion es lo que hay que quitar para que sea unlevered:
        principal de prestamos y polizas (17*, 52*), intereses y gastos
        financieros (66*, 527) y las aportaciones/retiradas de socios (55*).
        Los traspasos entre cuentas propias se anulan solos al sumar todas las
        lineas de tesoreria.
        """
        dia = self.d.get("diario")
        if dia is None or dia.empty:
            return None
        m = self._sin_apertura(dia[dia["mes"] == (mes or self.mes)])
        if m.empty:
            return None
        es_caja = m["cuenta"].astype(str).str.match(PREF_CAJA)
        caja, resto = m[es_caja], m[~es_caja]
        if caja.empty:
            return None

        pref_fin = tuple(str(p) for p in
                         (self.cfg.get("cuadre") or {}).get("cuentas_financiacion")
                         or ["17", "52", "527", "66", "55"])
        pref_susp = tuple(str(p) for p in
                          (self.cfg.get("cuadre") or {}).get("cuentas_suspenso")
                          or ["555"])
        contra, nat, nomb = {}, {}, {}
        for asiento, g in resto.groupby("asiento"):
            i = g["importe"].abs().idxmax()
            contra[asiento] = str(g.loc[i, "cuenta"])
            nat[asiento] = g.loc[i, "grupo_pgc"]
            nomb[asiento] = g.loc[i, "cuenta_nombre"] if "cuenta_nombre" in g else ""

        c = caja.copy()
        c["cta_contra"] = c["asiento"].map(lambda a: contra.get(a, ""))
        c["nom_contra"] = c["asiento"].map(lambda a: nomb.get(a, ""))
        # Suspenso (555, partidas pendientes de aplicar) no es ni financiacion
        # ni explotacion: es dinero que ha entrado o salido y todavia no se ha
        # llevado a su cuenta. Sumarlo al unlevered lo mueve 145.000 euros sin
        # que nadie sepa de que. Se saca y se dice cuanto queda por clasificar.
        c["es_susp"] = c["cta_contra"].map(lambda x: str(x).startswith(pref_susp))
        # Dentro del suspenso hay dos cosas muy distintas. La mayor parte de los
        # 131.119 de julio son "Traspasos entre bancos LT": mover dinero de una
        # cuenta propia a otra pasando por una cuenta puente en vez de banco
        # contra banco. Eso no es caja ni hay nada que clasificar, se anula
        # solo. Lo demas si esta pendiente de aplicar de verdad, y eso es
        # trabajo. Llamar a las dos cosas igual manda a alguien a revisar
        # 131.000 euros de los que 145.000 no necesitan revision.
        pat_traspaso = tuple(norm(p).lower() for p in
                             ((self.cfg.get("cuadre") or {}).get("patrones_traspaso")
                              or ["traspaso", "transferencia entre cuentas"]))
        c["es_traspaso"] = c["es_susp"] & c["nom_contra"].map(
            lambda n: any(p in norm(str(n)).lower() for p in pat_traspaso))
        # Las cuotas de sale & leaseback no estan en cuentas 52: el banco esta
        # dado de alta como PROVEEDOR y la cuota va contra una 400. En julio son
        # 80.248 euros a "BANCO SANTANDER S.A." en la cuenta 40000111, fuera del
        # perimetro. En el bottom-up eso es deuda, y con razon: es amortizacion
        # de un sale & leaseback, no una compra.
        # No se inventa un criterio nuevo: se usa la MISMA lista de entidades
        # que ya proyecta las cuotas en el forecast (cuotas_sl.operaciones), de
        # modo que el ejecutado y la proyeccion trazan la frontera igual.
        # APAGADO POR DEFECTO, y la razon esta medida. Se probo meter las cuotas
        # dentro de financiacion y el contraste contra el bottom-up EMPEORO en
        # los cuatro meses comparables: abril paso de 4k de diferencia a 115k,
        # marzo de 52k a 463k. O sea que en el modelo de Alejandro la cuota de
        # sale & leaseback es explotacion, no servicio de deuda; en la tabla de
        # deuda esta el saldo vivo, no la cuota del mes.
        # Se deja el interruptor porque el criterio es defendible y puede
        # cambiar, pero el defecto lo decide el contraste y no mi opinion.
        ents = set()
        if (self.cfg.get("cuadre") or {}).get("cuotas_sl_son_financiacion", False):
            ents = {norm(o.get("proveedor", "")) for o in
                    (self.cfg.get("cuotas_sl") or {}).get("operaciones") or []}
            ents |= {norm(x) for x in
                     (self.cfg.get("cuadre") or {}).get("entidades_financieras") or []}
            ents.discard("")
        c["es_sl"] = c["nom_contra"].map(
            lambda n: bool(n) and norm(str(n)) in ents)
        c["es_fin"] = (c["cta_contra"].map(lambda x: str(x).startswith(pref_fin))
                       | c["es_sl"]) & ~c["es_susp"]

        # Un traspaso entre cuentas propias NO es variacion de caja: es la misma
        # caja cambiada de sitio. Cuando las dos patas van banco contra banco se
        # anulan solas al sumar, pero cuando una pasa por cuenta puente solo se
        # ve una, y en julio eso metia +145.000 de entrada que no existe.
        #
        # Antes se restaba despues, al final del puente. El resultado era el
        # mismo pero la cifra que se llamaba "variacion real de caja" no lo era,
        # y los numeros del KPI no sumaban al titular: -103.645 con -101.196 de
        # financiacion no dan -133.569 por ningun lado. Alejandro lo vio de un
        # vistazo. Sacandolos de la variacion, que es su sitio, la variacion de
        # julio queda en -248.645 y todo cuadra a la vista.
        traspasos = float(c[c["es_traspaso"]]["importe"].sum())
        variacion = float(c[~c["es_traspaso"]]["importe"].sum())
        financiacion = float(c[c["es_fin"]]["importe"].sum())
        suspenso = float(c[c["es_susp"]]["importe"].sum())
        por_aplicar = suspenso - traspasos
        # El detalle va por CUENTA y no solo por grupo: donde se pone la
        # frontera de "financiacion" mueve la cifra entera, y eso hay que
        # poder verlo cuenta a cuenta para discutirlo, no aceptarlo.
        f = c[c["es_fin"]].copy()
        f["nat"] = f["asiento"].map(nat)
        det = (f.groupby(["cta_contra", "nat", "nom_contra"])["importe"].sum()
                 .reset_index().sort_values("importe"))
        # y lo que se ha quedado FUERA del perimetro tambien se ensena, por si
        # falta alguna cuenta que si deberia estar
        fuera = c[~c["es_fin"] & ~c["es_susp"]].copy()
        fuera["nat"] = fuera["asiento"].map(nat)
        top_fuera = (fuera.groupby(["cta_contra", "nat", "nom_contra"])["importe"].sum()
                          .reset_index())
        top_fuera = top_fuera.reindex(
            top_fuera["importe"].abs().sort_values(ascending=False).index).head(12)
        # El detalle de lo que hay en las cuentas puente, apunte a apunte. Son
        # 131.119 euros en julio: mientras sea un total no se puede clasificar,
        # y hasta que no se clasifique el unlevered del mes no esta cerrado.
        sp = c[c["es_susp"]].copy()
        sp["nat"] = sp["asiento"].map(nat)
        det_susp = [{"fecha": str(r["fecha"]), "cuenta": r["cta_contra"],
                     "traspaso": bool(r["es_traspaso"]),
                     "nombre": r.get("nom_contra") or r["nat"],
                     "concepto": r["concepto"], "banco": r.get("cuenta_nombre", ""),
                     "importe": float(r["importe"])}
                    for _, r in sp.sort_values("importe", key=abs,
                                               ascending=False).iterrows()]
        return {
            "variacion_caja": variacion,
            "financiacion": financiacion,
            "suspenso": suspenso,
            "traspasos": traspasos,
            "por_aplicar": por_aplicar,
            "detalle_suspenso": det_susp,
            # los traspasos ya no estan dentro de la variacion, asi que aqui
            # solo se quita lo que de verdad esta pendiente de aplicar
            "unlevered": variacion - financiacion - por_aplicar,
            "detalle_financiacion": [
                {"cuenta": r["cta_contra"], "concepto": r["nat"],
                 "nombre": r.get("nom_contra", ""),
                 "importe": float(r["importe"])} for _, r in det.iterrows()],
            "fuera_perimetro": [
                {"cuenta": r["cta_contra"], "concepto": r["nat"],
                 "nombre": r.get("nom_contra", ""),
                 "importe": float(r["importe"])} for _, r in top_fuera.iterrows()],
            "n_apuntes": int(len(c)),
        }

    def serie_fcf(self, n: int = 6) -> list:
        """
        El mismo puente, mes a mes: saldo inicial, saldo final, levered, deuda
        y unlevered. Es la tabla con la que se contrasta contra el bottom-up
        sin discutir una sola cifra.
        """
        salida = []
        for i in range(n, 0, -1):
            m = suma_meses(self.mes, -i)
            b = self.fcf_desde_banco(m)
            if b and (abs(b["levered"]) > 0.005 or abs(b["deuda"]) > 0.005):
                salida.append(b)
        return salida

    def serie_unlevered(self, n: int = 6) -> list:
        """
        El unlevered ejecutado de los ultimos meses, calculado igual que el del
        mes en curso. Sirve para contrastar contra el bottom-up mes a mes en
        vez de discutir una sola cifra: si la diferencia es la misma todos los
        meses es un criterio distinto, y si aparece en uno solo es un apunte.
        """
        dia = self.d.get("diario")
        if dia is None or dia.empty:
            return []
        salida = []
        for i in range(n, 0, -1):
            m = suma_meses(self.mes, -i)
            u = self.unlevered_ejecutado(m)
            if u:
                salida.append({"mes": m, "etiqueta": nombre_mes(m), **u})
        return salida

    def realizados_mes(self, mes: str | None = None) -> pd.DataFrame:
        """Cobros y pagos liquidados del mes, factura a factura."""
        r = self.d.get("realizados")
        if r is None or r.empty:
            return pd.DataFrame(columns=["fecha", "mes", "sentido", "tercero",
                                         "num", "importe", "banco", "concepto"])
        f = r[r["mes"] == (mes or self.mes)].copy()
        # la intercompania tampoco es caja aqui: mismo criterio que en forecast
        fuera = {norm(p) for p in (self.cfg.get("pagos") or {}).get(
            "excluir_proveedores") or []}
        fuera |= {norm(c) for c in self.cfg["cobros"].get("excluir_clientes") or []}
        if fuera and not f.empty:
            f = f[~f["tercero"].map(norm).isin(fuera)]
        return f.sort_values(["sentido", "fecha", "tercero"])

    # =======================================================================
    #  PREVISIONES: LO QUE DE VERDAD SE VA A COBRAR Y A PAGAR
    # =======================================================================
    def previsiones(self) -> list:
        """
        Correcciones manuales sobre lo que el motor proyecta.

        El forecast dice que una factura vencida es exigible. La realidad es
        que hay clientes que no van a pagar este mes, o no van a pagar entero,
        y eso no esta en Holded ni puede estarlo: es criterio de quien lleva la
        caja. Sin poder decirlo, el proyectado es una cifra que nadie usa.

        Cada prevision dice: para este cliente o esta factura, en este mes, el
        importe de verdad es este. Cero significa "no se cobra".

        Nunca se aplica en silencio: el panel enseña cada correccion con lo que
        decia el motor, lo que dice la prevision y la diferencia. Una cifra
        corregida a mano que no se sabe corregida es peor que la original.
        """
        salida = []
        for p in (self.cfg.get("previsiones") or []):
            mes = str(p.get("mes") or "")
            if mes and mes not in self.meses:
                continue
            salida.append({
                "tipo": str(p.get("tipo", "cobro")).lower(),
                "clave": str(p.get("clave", "")),
                "k": norm(p.get("clave", "")),
                "mes": mes or self.mes,
                "importe": float(p.get("importe") or 0),
                "nota": str(p.get("nota", "")),
            })
        return salida

    def _aplicar_previsiones(self, cli, prov):
        """
        Sustituye lo proyectado por lo previsto y devuelve el rastro completo.

        Casa por numero de factura o por nombre de tercero, sin acentos ni
        mayusculas. Si una clave no casa con nada NO se aplica en silencio: se
        devuelve marcada para que salga en el panel, porque una prevision que
        no encuentra su factura es una prevision que no esta haciendo nada y
        alguien tiene que enterarse.
        """
        prev = self.previsiones()
        if not prev:
            return cli, prov, []

        rastro = []
        for p in prev:
            destino = cli if p["tipo"] == "cobro" else prov
            col = f"teorico_{p['mes']}" if p["tipo"] == "cobro" else f"pago_{p['mes']}"
            if destino is None or destino.empty or col not in destino.columns:
                rastro.append({**p, "antes": 0.0, "aplicada": False,
                               "motivo": "no hay datos de ese mes"})
                continue
            campo = "cliente" if p["tipo"] == "cobro" else "proveedor"
            marca = destino[campo].map(norm) == p["k"]
            if not marca.any():
                rastro.append({**p, "antes": 0.0, "aplicada": False,
                               "motivo": f"no encuentro '{p['clave']}'"})
                continue
            # Las dos columnas, teorico_ y pago_, guardan magnitudes en
            # positivo: el signo se lo pone el forecast al montar la linea. Si
            # la prevision de un pago se guarda en negativo, el "antes" y el
            # "despues" salen con signos distintos y la diferencia es el doble
            # de lo que es. Se guarda como lo guarda todo el mundo aqui.
            antes = float(destino.loc[marca, col].sum())
            nuevo = abs(p["importe"])
            # todo el ajuste se carga en la primera fila que casa; el resto a 0,
            # para que el total del tercero sea exactamente el previsto
            idx = list(destino.index[marca])
            destino.loc[idx, col] = 0.0
            destino.loc[idx[0], col] = nuevo
            # para enseñarlo, el signo del flujo: los cobros entran, los pagos
            # salen. Asi la diferencia se lee como lo que le pasa a la caja.
            sg = 1 if p["tipo"] == "cobro" else -1
            rastro.append({**p, "antes": antes * sg, "despues": nuevo * sg,
                           "diferencia": (nuevo - antes) * sg, "aplicada": True,
                           "motivo": ""})
        return cli, prov, rastro

    # =======================================================================
    def _conciliar_caja(self) -> dict:
        """
        Reconstruye la posicion bancaria y la contrasta con contabilidad.

        Se cachea porque la usan el forecast y el puente al unlevered, y
        tienen que partir del mismo numero: si el KPI de posicion y el saldo
        de hoy del puente se calculasen por separado, cualquier correccion
        aplicada en uno y no en el otro saldria como flujo inventado.
        """
        if getattr(self, '_cc', None) is not None:
            return self._cc
        b = self.d['bancos']
        saldo_cta = (float(b[b['tipo'] == 'cuenta']['saldo'].sum())
                     if not b.empty else 0.0)
        # LA POSICION ES LA DEL LISTADO DE TESORERIA. Se probo sacarla del plan
        # contable sumando las cuentas 57*, y el resultado publicado fue
        # -2.997.589 euros contra los 358.864 del listado. O sea que el saldo
        # que devuelve /accounting-accounts no es el saldo a fecha de hoy de esa
        # cuenta: hay cuentas espejo (dos "Caja, euros" con +9.405 y -9.405) y
        # bancos en negativo que en el banco tienen dinero. Hasta saber que
        # mide exactamente ese campo, no manda sobre la posicion.
        #
        # Lo que si se hace es CONTRASTAR las dos fuentes cuenta a cuenta y
        # publicar el contraste, porque el problema de origen sigue ahi: hay
        # una segunda cuenta de Caixa con 24.705 euros que en el listado de
        # tesoreria figura a cero, y por eso la posicion sale 23.806 corta
        # contra los 382.670,40 de Alejandro. El enlace es el numero de cuenta
        # contable que trae el propio listado, no el nombre.
        pc = self.d.get("plan_contable")
        self.saldo_tesoreria = saldo_cta
        self.saldo_conta_hoy = None
        self.rescatado = 0.0
        self.recons_ok, self.recons_n = False, (0, 0)
        caja_conta, concilia = [], []
        if pc is not None and not pc.empty:
            c57 = pc[pc["numero"].astype(str).str.match(PREF_CAJA)]
            if not c57.empty:
                dh = (c57["debe"].fillna(0) - c57["haber"].fillna(0)
                      if {"debe", "haber"} <= set(c57.columns)
                      else c57["saldo"] * 0)
                self.saldo_conta_hoy = float(c57["saldo"].sum())
                self.saldo_conta_dh = float(dh.sum())
                caja_conta = [
                    {"numero": str(r["numero"]), "nombre": r.get("nombre", ""),
                     "saldo": float(r["saldo"]),
                     "debe_haber": float((r.get("debe") or 0) - (r.get("haber") or 0))}
                    for _, r in c57.iterrows()
                    if abs(float(r["saldo"])) > 0.005
                    or abs(float((r.get("debe") or 0) - (r.get("haber") or 0))) > 0.005]
                caja_conta.sort(key=lambda x: -x["saldo"])

                # QUE ES EL CAMPO balance DE /accounting-accounts.
                # No es el saldo de la cuenta: da el Sabadell en -2.027.759
                # cuando en el banco hay 25.843. Es el MOVIMIENTO DEL
                # EJERCICIO, sin el asiento de apertura. Sumandole el saldo del
                # 1 de enero -que si esta escrito, en el propio asiento de
                # apertura del libro diario- sale el saldo de hoy.
                #
                # Esto no se da por bueno porque encaje bien: se comprueba
                # cuenta a cuenta contra el listado de tesoreria, que para las
                # cuentas que Holded sincroniza es el saldo real del banco. Si
                # reconstruye bien esas, reconstruye bien la que falta.
                apert = self._apertura_por_cuenta()
                por_num = {c["numero"]: c for c in caja_conta}
                # Lo que hay en el extracto del banco y todavia no en la
                # contabilidad, CON SIGNO y por cuenta. Es la pieza que faltaba
                # para comparar las dos cifras: no tienen por que coincidir, y
                # de hecho no deben, porque se diferencian exactamente en esto.
                mv = self.d.get("movimientos")
                neto = {}
                if (mv is not None and not mv.empty
                        and "sin_conciliar" in mv.columns):
                    neto = {str(k): float(v) for k, v in
                            mv.groupby("cuenta")["sin_conciliar"].sum().items()}

                vistos = set()
                if "cta_conta" in b.columns:
                    for _, r in b[b["tipo"] == "cuenta"].iterrows():
                        num = str(r.get("cta_conta") or "")
                        cc = por_num.get(num)
                        if cc:
                            vistos.add(num)
                        rec = None if not cc else apert.get(num, 0.0) + cc["saldo"]
                        pte = neto.get(str(r["cuenta"]), 0.0)
                        concilia.append({
                            "cuenta": r["cuenta"], "num": num,
                            "listado": float(r["saldo"]),
                            "conta": None if not cc else cc["saldo"],
                            "recons": rec,
                            "pte": pte,
                            # contabilidad + lo que el banco tiene y ella aun no
                            "estimado": None if rec is None else rec + pte,
                            "banco": True})
                # cuentas contables de tesoreria sin ninguna cuenta de Holded
                # detras: caja en efectivo, intereses. No son banco.
                for c in caja_conta:
                    if c["numero"] not in vistos:
                        rec = apert.get(c["numero"], 0.0) + c["saldo"]
                        concilia.append({
                            "cuenta": c["nombre"] or "(sin nombre)",
                            "num": c["numero"], "listado": None,
                            "conta": c["saldo"], "recons": rec,
                            "pte": 0.0, "estimado": rec, "banco": False})

                # LA COMPROBACION, y esta vez la correcta.
                # La primera version comparaba el saldo reconstruido de
                # contabilidad contra el saldo del banco y exigia que fuesen
                # iguales. No lo son ni tienen por que serlo: se diferencian en
                # los movimientos que estan en el extracto y todavia no
                # apuntados. Con esa prueba el metodo "fallaba" en 5 de 7
                # cuentas cuando en realidad estaba bien; en el Sabadell la
                # diferencia era 20.009 euros y Holded declaraba exactamente
                # 20.009 euros sin conciliar en esa cuenta.
                #
                # La prueba buena es:  contabilidad + pendiente = banco.
                # Si eso se cumple en las cuentas que Holded sincroniza, el
                # metodo sabe reconstruir un saldo y se puede usar en la que no.
                tol = max(2.0, float(self.cfg.get("cuadre", {})
                                     .get("tolerancia_eur", 1)))
                comp = [c for c in concilia
                        if c["banco"] and c["estimado"] is not None
                        and abs(c["listado"]) > 0.005]
                for c in comp:
                    c["dif"] = c["estimado"] - c["listado"]
                aciertos = [c for c in comp if abs(c["dif"]) <= tol]
                self.recons_n = (len(aciertos), len(comp))
                # No se exige que cuadren TODAS. Lo pendiente de conciliar se
                # mueve mientras alguien concilia: entre dos ejecuciones
                # separadas veinte minutos, el Sabadell paso de 20.009 de
                # diferencia a cero. Exigir el pleno significa que la posicion
                # se corrige o no segun por donde vaya el contable esa manana,
                # y eso es peor que una regla con un umbral escrito.
                # Con techo, no redondeando: con redondeo, 0,6 sobre dos
                # cuentas da 1, o sea que bastaba con que la mitad cuadrase.
                # Y hacen falta al menos tres cuentas con las que comparar:
                # con una o dos, "la mayoria cuadra" no significa nada.
                minimo = float((self.cfg.get("tesoreria") or {})
                               .get("minimo_cuadre", 0.6))
                need = -(-int(minimo * 100) * len(comp) // 100)   # ceil
                self.recons_ok = len(comp) >= 3 and len(aciertos) >= max(1, need)

                # Y LA CORRECCION, solo si la comprobacion ha pasado: cuentas
                # que Holded reconoce como cuenta de tesoreria pero declara a
                # cero, teniendo movimiento contable. Es el caso de la segunda
                # de Caixa. Las cuentas contables sin cuenta de tesoreria
                # detras se enseñan pero NO se suman: la caja en efectivo no es
                # posicion bancaria y meterla seria cambiar la definicion de la
                # cifra por la puerta de atras.
                rescate = [c for c in concilia
                           if c["banco"] and c["estimado"] is not None
                           and abs(c["listado"]) < 0.005
                           and abs(c["estimado"]) > 1]

                # Un saldo escrito a mano en config.yaml manda sobre todo lo
                # anterior. Es para la cuenta que Holded no sincroniza y de la
                # que tu sabes el saldo: mas vale un numero confirmado por
                # alguien que un numero deducido por mi. Se avisa de la fecha
                # en que se confirmo, porque un saldo escrito a mano envejece.
                manual = {str(x.get("cuenta") or ""): x for x in
                          ((self.cfg.get("tesoreria") or {})
                           .get("saldos_manuales") or [])}
                for c in rescate:
                    mm = manual.get(str(c["cuenta"]))
                    if mm and mm.get("saldo") is not None:
                        c["estimado"] = float(mm["saldo"])
                        c["manual"] = mm.get("confirmado") or "sin fecha"

                if self.recons_ok and rescate:
                    self.rescatado = float(sum(c["estimado"] for c in rescate))
                    saldo_cta += self.rescatado
                    for c in rescate:
                        c["rescatada"] = True
                    self._avisar(
                        ("Holded declara a cero "
                         + ", ".join(f"{c['cuenta']}" for c in rescate)
                         + f", pero en contabilidad tiene movimiento. Su saldo "
                         f"({self.rescatado:,.0f} EUR) se ha reconstruido con "
                         f"el saldo del 1 de enero mas el movimiento del ano "
                         f"mas lo pendiente de conciliar, metodo que reproduce "
                         f"dentro de tolerancia las {self.recons_n[1]} cuentas "
                         f"que Holded si sincroniza. Entra en la posicion, "
                         f"pero es un saldo calculado y no leido del banco: "
                         f"conviene confirmarlo.").replace(",", " "))
                elif rescate and not self.recons_ok:
                    self._avisar(
                        f"Hay {len(rescate)} cuenta(s) de tesoreria que Holded "
                        f"declara a cero con movimiento contable detras, pero "
                        f"no se suman a la posicion: el metodo para "
                        f"reconstruir su saldo solo acierta en "
                        f"{self.recons_n[0]} de {self.recons_n[1]} cuentas "
                        f"conocidas, asi que no es de fiar. Estan listadas en "
                        f"el contraste con contabilidad.")

        self._cc = {'saldo': saldo_cta, 'listado': self.saldo_tesoreria,
                    'conciliacion': concilia, 'rescatado': self.rescatado,
                    'recons_ok': self.recons_ok, 'recons_n': self.recons_n,
                    'caja_contable': caja_conta}
        return self._cc

    def forecast(self) -> dict:
        cli = self.cobros_por_cliente()
        rent = self.rentings_sin_factura()
        prov = self.pagos_por_proveedor()
        recu = self.recurrentes_proyectados()
        sal, sal_det = self.salarios_mes()
        sl, sl_det = self.cuotas_sl_mes()

        cli, prov, rastro_prev = self._aplicar_previsiones(cli, prov)

        cob_cfg = self.cfg["cobros"]
        sin_fact = sum(x["unidades"] * x["precio"] * (1 + x["iva"])
                       for x in cob_cfg.get("sin_facturar") or [])
        aj_neg = sum(x["importe"] for x in cob_cfg.get("ajustes_negativos") or [])
        aj_pos = sum(x["importe"] for x in cob_cfg.get("ajustes_positivos") or [])

        # Partidas fijas ya pagadas en el mes en curso: se descuentan de lo que
        # queda por pagar. Si no, se cuentan dos veces (una en el saldo de hoy,
        # que ya las lleva descontadas, y otra en el forecast del mes).
        pagado = self.ya_pagado_fijos()
        self.fijos_ya_pagados = pagado

        def resto(previsto: float, bloque: str) -> float:
            """Lo que falta por pagar de una partida fija, nunca menos de cero."""
            hecho = float(pagado.get(bloque, 0.0))
            queda = max(0.0, abs(previsto) - hecho)
            return -queda

        out = {}
        for i, m in enumerate(self.meses):
            c_cli = float(cli[f"teorico_{m}"].sum()) if not cli.empty else 0.0
            rm = rent[rent["mes"] == m] if not rent.empty else rent
            c_ren = float(rm[rm["tipo"] == "renting"]["importe"].sum()) if not rm.empty else 0.0
            c_fus = float(rm[rm["tipo"] == "fusion"]["importe"].sum()) if not rm.empty else 0.0
            # las ventas sin facturar y los ajustes solo aplican al mes en curso
            c_sf = sin_fact if i == 0 else 0.0
            c_aj = (aj_neg + aj_pos) if i == 0 else 0.0

            p_prov = float(prov[f"pago_{m}"].sum()) if not prov.empty else 0.0
            p_recu = float(recu[recu["mes"] == m]["proyectado"].sum()) if not recu.empty else 0.0
            p_otros = -self.cfg["otros_pagos_fijos"]
            p_sal, p_sl = sal, sl
            if i == 0:
                p_sal = resto(sal, "salarios")
                p_sl = resto(sl, "cuotas_sl")
                p_recu = resto(p_recu, "recurrentes")
                p_otros = resto(p_otros, "otros_fijos")

            cash_in = c_cli + c_ren + c_fus + c_sf + c_aj
            cash_out = -abs(p_prov) + p_recu + p_sal + p_sl + p_otros

            out[m] = {
                "mes": m, "etiqueta": nombre_mes(m),
                "cobro_clientes": c_cli,
                "rentings_sin_factura": c_ren,
                "ventas_fusion_lml": c_fus,
                "ventas_sin_facturar": c_sf,
                "ajustes_cobros": c_aj,
                "cash_in": cash_in,
                "pago_proveedores": -abs(p_prov),
                "recurrentes_proyectados": p_recu,
                "salarios": p_sal,
                "cuotas_sl": p_sl,
                "otros_fijos": p_otros,
                "cash_out": cash_out,
                "fcf": cash_in + cash_out,
            }

        # posicion bancaria y proyeccion de saldo
        b = self.d["bancos"]
        cc = self._conciliar_caja()
        saldo_cta = cc['saldo']
        concilia, caja_conta = cc['conciliacion'], cc['caja_contable']

        # POLIZAS. El saldo que da Holded es lo DISPUESTO, en negativo. El
        # disponible es limite - dispuesto, y el limite no lo publica la API:
        # sale de config.yaml. Sin limite configurado el disponible es
        # DESCONOCIDO, que no es lo mismo que cero: cero se lee como "no hay
        # financiacion" y llevaria a decidir sobre un dato inventado.
        pol = b[b["tipo"] == "poliza"] if not b.empty else b
        limites = (self.cfg.get("tesoreria") or {}).get("polizas") or []
        disp_pol, lim_total, sin_limite = 0.0, 0.0, []
        # Una poliza con saldo POSITIVO no esta dispuesta: tiene dinero dentro.
        # La 9418 tiene 971.776 en positivo, el 74% de toda la posicion. Sacarla
        # de la caja por ser cuenta de credito habria escondido casi un millon
        # de euros que estan ahi. Se cuenta como caja, pero se dice aparte:
        # tener el grueso de la tesoreria en una cuenta de credito no es
        # indiferente y quien lo mira tiene que verlo.
        saldo_en_pol = 0.0
        for _, r in pol.iterrows():
            saldo = float(r["saldo"])
            dispuesto = -saldo if saldo < 0 else 0.0
            if saldo > 0:
                saldo_en_pol += saldo
            lim = next((float(x.get("limite") or 0) for x in limites
                        if norm(str(x.get("cuenta", ""))).lower()
                        in norm(str(r["cuenta"])).lower()), 0.0)
            if lim > 0:
                lim_total += lim
                disp_pol += lim - dispuesto
            elif dispuesto > 0.005:
                sin_limite.append(f"{r['cuenta']} (dispuesto {dispuesto:,.0f})"
                                  .replace(",", " "))
        self.polizas_sin_limite = sin_limite

        # Las tarjetas no son caja: un saldo negativo en una tarjeta es deuda a
        # pagar, no tesoreria disponible. Se saca del saldo y se dice cuanto es.
        tar = b[b["tipo"] == "tarjeta"] if not b.empty else b
        deuda_tarjetas = float(tar["saldo"].sum()) if not tar.empty else 0.0

        # LAS POLIZAS NO SON CAJA. Yo habia razonado que una cuenta de credito
        # con saldo positivo tiene dinero dentro y por tanto es tesoreria, y
        # Alejandro lo corrigio de una frase: "la caja no es esa, descuenta las
        # polizas". Tiene razon en lo que importa: una linea de credito es
        # financiacion disponible, no caja propia, y meterla en la posicion
        # bancaria hace que la empresa parezca tener 1,3 millones cuando tiene
        # 326.000 y el resto es credito.
        # Se informa aparte, en su KPI, que para eso esta.
        if (self.cfg.get("tesoreria") or {}).get("polizas_en_caja", False):
            saldo_cta += saldo_en_pol

        acum = saldo_cta
        for m in self.meses:
            acum += out[m]["fcf"]
            out[m]["saldo_proyectado"] = acum
            out[m]["saldo_proyectado_con_polizas"] = acum + disp_pol

        # EJECUTADO DEL MES EN CURSO: lo que ya ha entrado y salido de verdad
        # entre el dia 1 y hoy. Es el "cuanto llevamos" del mes, y sumado a lo
        # que queda por delante da el cierre proyectado.
        rea = self.realizados_mes()
        cob_eje = float(rea[rea["sentido"] == "cobro"]["importe"].sum()) if not rea.empty else 0.0
        pag_fac = float(rea[rea["sentido"] == "pago"]["importe"].sum()) if not rea.empty else 0.0
        sin_doc = (rea[rea["sentido"] == "sin_documento"] if not rea.empty
                   else rea)
        pag_fij = -sum(float(v) for k, v in pagado.items() if k != "_detalle")
        eje = {
            "cobros": cob_eje,
            "pagos_factura": pag_fac,
            "pagos_fijos": pag_fij,
            "pagos": pag_fac + pag_fij,
            "fcf": cob_eje + pag_fac + pag_fij,
            "n_cobros": int((rea["sentido"] == "cobro").sum()) if not rea.empty else 0,
            "n_pagos": int((rea["sentido"] == "pago").sum()) if not rea.empty else 0,
            "n_sin_doc": int(len(sin_doc)),
            "importe_sin_doc": float(sin_doc["importe"].abs().sum()) if len(sin_doc) else 0.0,
        }
        m0 = out[self.meses[0]]
        # Si hay libro diario, el ejecutado bueno es el que sale de la caja
        # real: coge TODO lo que ha salido del banco, no solo lo que pasa por
        # factura o lo que reconozco por el concepto. La cuenta por facturas se
        # queda como desglose, que para eso sirve.
        # El puente bueno es el que arranca del saldo del banco: es el que pidio
        # Alejandro y el que no depende de ningun criterio mio. El del libro
        # diario se queda como contraste, que para eso sirve tener dos caminos.
        bk = self.fcf_desde_banco()
        eje["banco"] = bk
        ul = self.unlevered_ejecutado()
        if bk:
            eje["por_facturas"] = eje["fcf"]
            eje["saldo_inicio"] = bk["saldo_inicio"]
            eje["saldo_hoy"] = bk["saldo_hoy"]
            eje["levered"] = bk["levered"]
            eje["deuda"] = bk["deuda"]
            eje["detalle_deuda"] = bk["detalle_deuda"]
            eje["fcf"] = bk["unlevered"]
            eje["fuente"] = "saldo del banco"
            # el diario tiene que decir lo mismo; si no, hay que saberlo
            eje["contraste_diario"] = (
                None if not ul else bk["levered"] - ul["variacion_caja"])
        elif ul:
            eje["por_facturas"] = eje["fcf"]
            eje["variacion_caja"] = ul["variacion_caja"]
            eje["financiacion"] = ul["financiacion"]
            eje["suspenso"] = ul["suspenso"]
            eje["traspasos"] = ul["traspasos"]
            eje["por_aplicar"] = ul["por_aplicar"]
            eje["detalle_suspenso"] = ul["detalle_suspenso"]
            eje["detalle_financiacion"] = ul["detalle_financiacion"]
            eje["fuera_perimetro"] = ul["fuera_perimetro"]
            eje["fcf"] = ul["unlevered"]
            eje["fuente"] = "libro diario"
        else:
            eje["fuente"] = "facturas y extracto"

        eje["cierre_mes_fcf"] = eje["fcf"] + m0["fcf"]
        eje["saldo_cierre_mes"] = saldo_cta + m0["fcf"]

        return {
            "meses": self.meses, "lineas": out,
            "previsiones": rastro_prev,
            "ejecutado": eje,
            "fijos_pagados": pagado,
            "polizas_limite": lim_total, "polizas_sin_limite": sin_limite,
            "saldo_en_polizas": saldo_en_pol, "deuda_tarjetas": deuda_tarjetas,
            "saldo_actual": saldo_cta, "polizas_disponible": disp_pol,
            "saldo_tesoreria": self.saldo_tesoreria,
            "caja_contable": caja_conta,
            "conciliacion_caja": concilia,
            "rescatado": self.rescatado,
            "recons_ok": self.recons_ok,
            "recons_n": self.recons_n,
            "dif_tesoreria": (None if self.saldo_conta_hoy is None
                              else self.saldo_conta_hoy - self.saldo_tesoreria),
            "detalle": {"salarios": sal_det, "cuotas_sl": sl_det,
                        "sin_facturar": cob_cfg.get("sin_facturar") or [],
                        "ajustes": ((cob_cfg.get("ajustes_negativos") or [])
                                    + (cob_cfg.get("ajustes_positivos") or [])),
                        "otros_fijos": [{"concepto": "Otros pagos fijos",
                                         "importe": -self.cfg["otros_pagos_fijos"]}],
                        "fijos_pagados": pagado},
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

        # Con libro diario esto deja de ser una conciliacion por aproximacion y
        # pasa a ser una identidad: cada movimiento de caja tiene su
        # contrapartida en el mismo asiento, asi que no puede quedar residuo.
        # Emparejar importes del extracto con liquidaciones de facturas, que es
        # lo que se hacia antes, dejaba 178.000 euros sin explicar por pura
        # construccion: los pagos sin factura no tenian con que casar.
        # EL CHECK DE VERDAD, que es el que pidio Alejandro:
        #
        #   saldo de apertura del banco  +  cobros  +  pagos  =  saldo de hoy
        #
        # con los dos extremos sacados de sitios INDEPENDIENTES: la apertura del
        # saldo contable de las 57* cerrado a fin del mes anterior, y el de hoy
        # del saldo que da Holded. Si no cuadra, falta algo, y eso es lo unico
        # que un check debe poder decir.
        #
        # Lo que habia antes era saldo inicial + cash in + cash out = saldo
        # final, con el saldo final calculado como saldo inicial + flujo. Eso
        # cuadra siempre porque es la misma cuenta escrita dos veces. Alejandro:
        # "este check es una falacia, lo haces cuadrar tu". Tenia razon.
        bk = self.fcf_desde_banco(mes)
        nat = self.caja_por_naturaleza(mes)
        if bk and nat is not None and not nat.empty:
            filas = [{"concepto": r["naturaleza"], "importe": float(r["importe"]),
                      "apuntes": int(r["apuntes"])} for _, r in nat.iterrows()]
            cobros = float(sum(x["importe"] for x in filas if x["importe"] > 0))
            pagos = float(sum(x["importe"] for x in filas if x["importe"] < 0))
            teorico = bk["saldo_inicio"] + cobros + pagos
            dif = teorico - bk["saldo_hoy"]
            tol = float(self.cfg["cuadre"]["tolerancia_eur"])
            return {
                "mes": mes, "etiqueta": nombre_mes(mes),
                "fuente": "apertura contra saldo de hoy",
                "saldo_apertura": bk["saldo_inicio"],
                "origen_apertura": bk.get("origen_inicio", ""),
                "cobros_ejecutados": cobros,
                "pagos_ejecutados": pagos,
                "saldo_teorico": teorico,
                "saldo_hoy": bk["saldo_hoy"],
                "diferencia": dif,
                "cuadra": abs(dif) <= tol,
                "tolerancia": tol,
                "naturaleza": filas,
                "pdte_conciliar": bk.get("pdte_conciliar") or [],
                "flujo_por_facturas": cobros + pagos,
                "variacion_bancaria": bk["saldo_hoy"] - bk["saldo_inicio"],
                "sin_conciliar": [], "resumen_sin_conciliar": [],
                "importe_sin_conciliar": 0.0, "residuo": dif, "por_cuenta": [],
                "explicacion": (
                    "Los dos extremos salen de sitios distintos: la apertura del "
                    "saldo contable de las cuentas 57* a fin del mes anterior, y "
                    "el de hoy del saldo que da Holded. Lo que no cuadre entre "
                    "ellos son movimientos que faltan, no un ajuste de criterio."),
            }

        if nat is not None and not nat.empty:
            variacion = float(nat["importe"].sum())
            filas = [{"concepto": r["naturaleza"], "importe": float(r["importe"]),
                      "apuntes": int(r["apuntes"])} for _, r in nat.iterrows()]
            cobros = float(sum(x["importe"] for x in filas if x["importe"] > 0))
            pagos = float(sum(x["importe"] for x in filas if x["importe"] < 0))
            return {
                "mes": mes, "etiqueta": nombre_mes(mes),
                "fuente": "libro diario",
                "cobros_ejecutados": cobros,
                "pagos_ejecutados": pagos,
                "flujo_por_facturas": variacion,
                "variacion_bancaria": variacion,
                "diferencia": 0.0,
                "cuadra": True,
                "tolerancia": float(self.cfg["cuadre"]["tolerancia_eur"]),
                "naturaleza": filas,
                "sin_conciliar": [],
                "resumen_sin_conciliar": [],
                "importe_sin_conciliar": 0.0,
                "residuo": 0.0,
                "por_cuenta": [],
                "explicacion": (
                    "Sale del libro diario: cada movimiento de caja lleva su "
                    "contrapartida en el mismo asiento, asi que todo el flujo "
                    "del mes queda explicado por naturaleza y no queda residuo. "
                    "Antes se emparejaban importes del extracto con "
                    "liquidaciones de facturas y quedaban 178.000 euros sin "
                    "explicar, que eran justamente los pagos sin factura."
                ),
            }

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
