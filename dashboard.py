# -*- coding: utf-8 -*-
"""
============================================================================
 LEASEIR - Generador del dashboard de caja (HTML autocontenido)
============================================================================
 Sin dependencias externas: todo el CSS y el JS van embebidos y los graficos
 son SVG generado en Python. Se abre en cualquier navegador y se puede enviar
 por correo tal cual.
============================================================================
"""
from __future__ import annotations

import html
import json
import os
from datetime import datetime, timezone

try:
    from zoneinfo import ZoneInfo
    MADRID = ZoneInfo("Europe/Madrid")
except Exception:                                   # pragma: no cover
    MADRID = None


def ahora_es() -> datetime:
    """
    Hora peninsular espanola. Los runners de GitHub van en UTC, asi que sin esto
    el sello del dashboard saldria dos horas atrasado en verano.
    """
    u = datetime.now(timezone.utc)
    return u.astimezone(MADRID) if MADRID else u

# ---------------------------------------------------------------------------
#  Paleta Leaseir
#  El petrol corporativo (#1f4d5c) es color de CHROMA, no de dato: su croma
#  (0.083) esta por debajo del suelo de 0.1 y en una barra leeria como gris.
#  Los datos usan una serie validada cuyo primer slot (#007e9e) es el teal mas
#  saturado que armoniza con la marca y pasa las seis comprobaciones
#  (banda de luminosidad, croma, separacion CVD, suelo de vision normal,
#  contraste). Verificado con validate_palette.js sobre superficie #fbfaf8.
# ---------------------------------------------------------------------------
P = {
    # marca
    "brand": "#1f4d5c", "brand2": "#2d6479", "brand3": "#3d7d92",
    # serie categorica validada
    "s1": "#007e9e", "s2": "#eb6834", "s3": "#1baf7a", "s4": "#eda100",
    "s5": "#e87ba4", "s7": "#1f4d5c",
    # estado
    "good": "#0ca30c", "warn": "#fab219", "serious": "#ec835a", "crit": "#d03b3b",
    # superficies y tinta
    "surface": "#ffffff", "plane": "#f4f2ef",
    "ink": "#141618", "ink2": "#4f585d", "muted": "#8a9196",
    "grid": "#e6e3df", "axis": "#c5c1bb", "border": "rgba(31,77,92,0.13)",
    "up": "#006300",
}


def eur(x, dec=0) -> str:
    if x is None:
        return "—"
    # sin esto salen "-0 €" cuando el importe es -0,004: un menos delante de un
    # cero, en un panel financiero, hace dudar de todo lo demas
    if abs(x) < 0.5 / (10 ** dec):
        x = 0.0
    s = f"{x:,.{dec}f}".replace(",", " ")
    return s + " €"


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


# ---------------------------------------------------------------------------
#  GRAFICOS SVG
# ---------------------------------------------------------------------------
def barras_h(datos, color=P["s1"], ancho=680, alto_barra=26, neg_color=None,
             fmt=eur, max_abs=None):
    """
    Barras horizontales con etiqueta directa (obligatorio: el azul/verde de la
    paleta va por debajo de 3:1 sobre superficie clara, la regla de relieve
    exige etiqueta visible).
    """
    if not datos:
        return '<p class="vacio">Sin datos.</p>'
    etiq_w, val_w = 250, 108
    plot = ancho - etiq_w - val_w
    m = max_abs or max((abs(v) for _, v in datos), default=1) or 1
    alto = len(datos) * alto_barra + 8
    out = [f'<svg viewBox="0 0 {ancho} {alto}" width="100%" height="{alto}" '
           f'role="img" class="chart">']
    for i, (nom, val) in enumerate(datos):
        y = i * alto_barra + 4
        w = max(2.0, abs(val) / m * plot)
        c = (neg_color or P["crit"]) if val < 0 else color
        nom_c = nom if len(str(nom)) <= 34 else str(nom)[:32] + "…"
        out.append(
            f'<text x="{etiq_w - 8}" y="{y + 15}" text-anchor="end" class="lbl">{esc(nom_c)}</text>'
            f'<rect x="{etiq_w}" y="{y + 3}" width="{w:.1f}" height="{alto_barra - 10}" '
            f'rx="4" fill="{c}"><title>{esc(nom)}: {fmt(val)}</title></rect>'
            f'<text x="{etiq_w + w + 7:.1f}" y="{y + 15}" class="val">{fmt(val)}</text>')
    out.append("</svg>")
    return "".join(out)


def waterfall(saldo_ini, pasos, ancho=760, alto=260):
    """Cascada de caja: saldo inicial, flujos de cada mes, saldo final."""
    puntos = [("Saldo hoy", saldo_ini, "total")]
    acum = saldo_ini
    for nom, val in pasos:
        puntos.append((nom, val, "flujo"))
        acum += val
    puntos.append(("Saldo proyectado", acum, "total"))

    vals, run = [], saldo_ini
    techos = [saldo_ini]
    for _, v, t in puntos[1:-1]:
        techos.append(run); run += v; techos.append(run)
    techos.append(acum)
    top = max(max(techos), 0) * 1.12
    bot = min(min(techos), 0) * 1.12 if min(techos) < 0 else 0
    rango = (top - bot) or 1

    pad_l, pad_b, pad_t = 78, 44, 16
    plot_h = alto - pad_b - pad_t
    plot_w = ancho - pad_l - 16
    paso = plot_w / len(puntos)
    bw = min(74, paso * 0.56)

    def Y(v): return pad_t + (top - v) / rango * plot_h

    out = [f'<svg viewBox="0 0 {ancho} {alto}" width="100%" height="{alto}" class="chart">']
    for f in range(5):
        v = bot + (top - bot) * f / 4
        y = Y(v)
        out.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{ancho-16}" y2="{y:.1f}" '
                   f'stroke="{P["grid"]}" stroke-width="1"/>'
                   f'<text x="{pad_l-8}" y="{y+4:.1f}" text-anchor="end" class="ax">'
                   f'{v/1000:,.0f}k</text>')
    out.append(f'<line x1="{pad_l}" y1="{Y(0):.1f}" x2="{ancho-16}" y2="{Y(0):.1f}" '
               f'stroke="{P["axis"]}" stroke-width="1.5"/>')

    run = 0.0
    for i, (nom, val, tipo) in enumerate(puntos):
        x = pad_l + i * paso + (paso - bw) / 2
        if tipo == "total":
            y0, y1 = Y(max(val, 0)), Y(min(val, 0))
            c = P["s7"]
            run = val
        else:
            ini, fin = run, run + val
            y0, y1 = Y(max(ini, fin)), Y(min(ini, fin))
            c = P["s3"] if val >= 0 else P["s2"]
            run = fin
        h = max(3.0, abs(y1 - y0))
        out.append(f'<rect x="{x:.1f}" y="{y0:.1f}" width="{bw:.1f}" height="{h:.1f}" rx="4" '
                   f'fill="{c}"><title>{esc(nom)}: {eur(val)}</title></rect>')
        out.append(f'<text x="{x+bw/2:.1f}" y="{y0-6:.1f}" text-anchor="middle" class="val">'
                   f'{val/1000:,.0f}k</text>')
        out.append(f'<text x="{x+bw/2:.1f}" y="{alto-24:.1f}" text-anchor="middle" class="ax">'
                   f'{esc(nom[:16])}</text>')
    out.append("</svg>")
    return "".join(out)


def barras_agrupadas(meses, series, ancho=760, alto=250):
    """series = [(nombre, color, [valores por mes])]"""
    pad_l, pad_b, pad_t = 78, 44, 16
    plot_h, plot_w = alto - pad_b - pad_t, ancho - pad_l - 16
    todos = [v for _, _, vs in series for v in vs] or [0]
    top = max(max(todos), 0) * 1.12
    bot = min(min(todos), 0) * 1.12 if min(todos) < 0 else 0
    rango = (top - bot) or 1
    def Y(v): return pad_t + (top - v) / rango * plot_h

    grupo = plot_w / len(meses)
    bw = min(52, (grupo * 0.72) / len(series))
    out = [f'<svg viewBox="0 0 {ancho} {alto}" width="100%" height="{alto}" class="chart">']
    for f in range(5):
        v = bot + (top - bot) * f / 4
        y = Y(v)
        out.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{ancho-16}" y2="{y:.1f}" '
                   f'stroke="{P["grid"]}" stroke-width="1"/>'
                   f'<text x="{pad_l-8}" y="{y+4:.1f}" text-anchor="end" class="ax">{v/1000:,.0f}k</text>')
    out.append(f'<line x1="{pad_l}" y1="{Y(0):.1f}" x2="{ancho-16}" y2="{Y(0):.1f}" '
               f'stroke="{P["axis"]}" stroke-width="1.5"/>')
    for gi, mes in enumerate(meses):
        base = pad_l + gi * grupo + (grupo - bw * len(series) - 2 * (len(series) - 1)) / 2
        for si, (nom, col, vs) in enumerate(series):
            v = vs[gi]
            x = base + si * (bw + 2)          # separador de 2px entre marcas
            y0, y1 = Y(max(v, 0)), Y(min(v, 0))
            h = max(2.0, abs(y1 - y0))
            out.append(f'<rect x="{x:.1f}" y="{y0:.1f}" width="{bw:.1f}" height="{h:.1f}" rx="4" '
                       f'fill="{col}"><title>{esc(nom)} · {esc(mes)}: {eur(v)}</title></rect>')
            out.append(f'<text x="{x+bw/2:.1f}" y="{(y0-6) if v>=0 else (y1+15):.1f}" '
                       f'text-anchor="middle" class="val">{v/1000:,.0f}k</text>')
        out.append(f'<text x="{pad_l+gi*grupo+grupo/2:.1f}" y="{alto-22:.1f}" '
                   f'text-anchor="middle" class="ax">{esc(mes)}</text>')
    out.append("</svg>")
    return "".join(out)


def leyenda(items):
    return ('<div class="leyenda">' + "".join(
        f'<span class="li"><i style="background:{c}"></i>{esc(n)}</span>' for n, c in items
    ) + "</div>")


# ---------------------------------------------------------------------------
#  BLOQUES
# ---------------------------------------------------------------------------
def kpi(titulo, valor, nota="", estado=""):
    cls = f" {estado}" if estado else ""
    return (f'<div class="kpi{cls}"><div class="k-t">{esc(titulo)}</div>'
            f'<div class="k-v">{valor}</div>'
            f'<div class="k-n">{esc(nota)}</div></div>')


def tabla(cabeceras, filas, alineacion=None, clases=None):
    al = alineacion or ["l"] + ["r"] * (len(cabeceras) - 1)
    th = "".join(f'<th class="{a}">{esc(c)}</th>' for c, a in zip(cabeceras, al))
    tr = []
    for i, f in enumerate(filas):
        cl = f' class="{clases[i]}"' if clases and clases[i] else ""
        tds = "".join(f'<td class="{a}">{c}</td>' for c, a in zip(f, al))
        tr.append(f"<tr{cl}>{tds}</tr>")
    return f'<table><thead><tr>{th}</tr></thead><tbody>{"".join(tr)}</tbody></table>'




def bloque_cuadre_proyeccion(filas, etiquetas):
    """saldo inicial + cash in + cash out = saldo final, mes a mes."""
    f, cl = [], []
    for r in filas:
        marca = ('<span class="chip ok">cuadra</span>' if r["cuadra"]
                 else f'<span class="chip crit">{eur(r["diferencia"])}</span>')
        f.append([esc(r["etiqueta"]), eur(r["saldo_inicial"]), eur(r["cash_in"]),
                  eur(r["cash_out"]), f'<b>{eur(r["fcf"])}</b>',
                  f'<b>{eur(r["saldo_final"])}</b>', marca])
        cl.append("")
    return tabla(["Mes", "Saldo inicial", "Cash in", "Cash out",
                  "Unlevered FCF", "Saldo final", "Check"], f, clases=cl)


def detalle_desplegable(grupos, cabeceras, alineacion=None, vacio="Sin movimientos."):
    """
    Una fila por tercero que se despliega y muestra sus facturas.
    grupos = [(titulo, resumen_html, [filas_de_factura]), ...]
    """
    if not grupos:
        return f'<p class="vacio">{esc(vacio)}</p>'
    out = []
    for titulo, resumen, filas in grupos:
        out.append(
            f'<details class="terc"><summary>'
            f'<span class="t-nom">{esc(titulo)}</span>'
            f'<span class="t-res">{resumen}</span>'
            f'<span class="t-n">{len(filas)} fra.</span></summary>'
            f'<div class="t-body">{tabla(cabeceras, filas, alineacion)}</div>'
            f'</details>')
    return "".join(out)


# ---------------------------------------------------------------------------
#  DASHBOARD
# ---------------------------------------------------------------------------
def construir(fc: dict, cuadre: dict, alertas: list, meta: dict) -> str:
    L, meses = fc["lineas"], fc["meses"]
    m0 = L[meses[0]]
    etiquetas = [L[m]["etiqueta"] for m in meses]

    # ---- KPIs -------------------------------------------------------------
    cli = fc["clientes"]
    prov = fc["proveedores"]
    pend_cobro = float(cli["pendiente_cobro"].sum()) if not cli.empty else 0.0
    retraso = float(cli["retraso"].sum()) if not cli.empty else 0.0
    vencido = float(prov["vencido"].sum()) if not prov.empty else 0.0
    saldo_fin = L[meses[-1]]["saldo_proyectado"]

    eje = fc.get("ejecutado") or {}
    saldo_cierre = eje.get("saldo_cierre_mes", m0["saldo_proyectado"])

    est_fcf = "ok" if eje.get("fcf", 0) >= 0 else "mal"
    est_fin = "ok" if saldo_cierre > 200_000 else ("aviso" if saldo_cierre > 0 else "mal")

    # Nota de pólizas. Holded no publica el limite, asi que sin limite escrito
    # en config no se puede decir el disponible. Decir "+ 0 €" seria mentir por
    # omision: se lee como que no hay financiacion, y no es lo mismo que no
    # saberlo.
    sin_lim = fc.get("polizas_sin_limite") or []
    if fc.get("polizas_limite"):
        nota_pol = (f"+ {eur(fc['polizas_disponible'])} disponible en pólizas "
                    f"sobre {eur(fc['polizas_limite'])} de límite")
    elif sin_lim:
        nota_pol = f"pólizas: {esc(', '.join(sin_lim))}, límite sin configurar"
    else:
        nota_pol = "sin pólizas"
    # Tener el grueso de la tesoreria dentro de una cuenta de credito no es
    # indiferente: se cuenta como caja pero se dice.
    if fc.get("saldo_en_polizas", 0) > 0.5:
        nota_pol += f" · de los cuales {eur(fc['saldo_en_polizas'])} están en cuenta de crédito"

    kpis = "".join([
        kpi("Posición bancaria hoy", eur(fc["saldo_actual"]), nota_pol),
        kpi(f"Unlevered FCF {m0['etiqueta']} · lo que llevamos",
            eur(eje.get("fcf", 0)),
            # los tres numeros tienen que sumar al titular a la vista, o el
            # lector deja de fiarse de todo lo demas
            (f"Caja {eur(eje.get('variacion_caja', 0))} menos financiación "
             f"{eur(eje.get('financiacion', 0))}"
             + (f" menos por aplicar {eur(eje.get('por_aplicar', 0))}"
                if abs(eje.get("por_aplicar", 0)) > 0.5 else "")
             if eje.get("fuente") == "libro diario" else
             f"Cobrado {eur(eje.get('cobros', 0))} · pagado {eur(eje.get('pagos', 0))}"),
            est_fcf),
        kpi(f"Saldo proyectado a cierre de {m0['etiqueta']}", eur(saldo_cierre),
            f"quedan {eur(m0['fcf'])} de flujo por delante", est_fin),
        kpi("Pendiente de cobro exigible", eur(pend_cobro),
            f"de los cuales {eur(retraso)} en retraso",
            "aviso" if retraso > 300_000 else ""),
        kpi("Vencido a proveedores", eur(-vencido),
            f"{int((prov['vencido'] > 0.01).sum()) if not prov.empty else 0} proveedores",
            "aviso" if vencido > 200_000 else ""),
    ])

    # ---- tabla forecast ---------------------------------------------------
    def fila(et, clave, tipo=""):
        vals = [L[m][clave] for m in meses]
        cel = [f'<span class="{"neg" if v < 0 else ""}">{eur(v)}</span>' for v in vals]
        return [f'<span class="{tipo}">{esc(et)}</span>'] + cel

    filas_fc, clases = [], []
    for et, k, cl in [
        ("Cobro de clientes", "cobro_clientes", ""),
        ("Rentings sin facturar", "rentings_sin_factura", ""),
        # Facturas FM: vienen de la fusion con LML. Estan facturadas, solo que
        # en otra sociedad, asi que no pueden ir en la linea de "sin facturar".
        ("Ventas financiadas desde LML (fusión)", "ventas_fusion_lml", ""),
        ("Ventas comprometidas sin facturar", "ventas_sin_facturar", ""),
        ("Ajustes sobre cobros", "ajustes_cobros", ""),
        ("CASH IN", "cash_in", "b"),
        ("Pago a proveedores", "pago_proveedores", ""),
        ("Gastos recurrentes proyectados", "recurrentes_proyectados", ""),
        ("Salarios y Seguridad Social", "salarios", ""),
        ("Cuotas S&amp;L y renting bancario", "cuotas_sl", ""),
        ("Otros pagos fijos", "otros_fijos", ""),
        ("CASH OUT", "cash_out", "b"),
        ("UNLEVERED FREE CASH FLOW", "fcf", "b tot"),
        ("Saldo proyectado (sin pólizas)", "saldo_proyectado", "b"),
        ("Saldo proyectado (con pólizas)", "saldo_proyectado_con_polizas", ""),
    ]:
        filas_fc.append(fila(et, k, "b" if "b" in cl else ""))
        clases.append("total" if "tot" in cl else ("sub" if "b" in cl else ""))

    tabla_fc = tabla(["Concepto"] + etiquetas, filas_fc, clases=clases)

    # ---- graficos ---------------------------------------------------------
    wf = waterfall(fc["saldo_actual"], [(L[m]["etiqueta"], L[m]["fcf"]) for m in meses])
    barras_mes = barras_agrupadas(etiquetas, [
        ("Cash in", P["s3"], [L[m]["cash_in"] for m in meses]),
        ("Cash out", P["s2"], [L[m]["cash_out"] for m in meses]),
        ("FCF", P["s1"], [L[m]["fcf"] for m in meses]),
    ])
    lg_mes = leyenda([("Cash in", P["s3"]), ("Cash out", P["s2"]), ("FCF", P["s1"])])

    # ---- cobros -----------------------------------------------------------
    if not cli.empty:
        top_c = cli.nlargest(12, "pendiente_cobro")
        g_cob = barras_h([(r["cliente"], r["pendiente_cobro"]) for _, r in top_c.iterrows()],
                         color=P["s1"])
        fil = []
        for _, r in cli.nlargest(25, "pendiente_cobro").iterrows():
            ret = r["retraso"]
            marca = (f'<span class="chip crit">{eur(ret)}</span>' if ret > 50_000
                     else (f'<span class="chip warn">{eur(ret)}</span>' if ret > 0.01
                           else '<span class="chip ok">al día</span>'))
            fil.append([esc(r["cliente"]), eur(r["pendiente_cobro"]), eur(r["cuota_mes"]),
                        marca] + [eur(r[f"teorico_{m}"]) for m in meses[1:]])
        t_cob = tabla(["Cliente", "Pendiente exigible", f"Cuota {m0['etiqueta']}", "Retraso"]
                      + [f"Teórico {e}" for e in etiquetas[1:]], fil)
    else:
        g_cob, t_cob = '<p class="vacio">Sin datos.</p>', ""

    # ---- pagos ------------------------------------------------------------
    if not prov.empty:
        top_p = prov.nlargest(12, "pendiente_total")
        g_pag = barras_h([(r["proveedor"], -r["pendiente_total"]) for _, r in top_p.iterrows()],
                         color=P["s2"], neg_color=P["s2"])
        fil = []
        for _, r in prov.nlargest(25, "pendiente_total").iterrows():
            v = r["vencido"]
            marca = (f'<span class="chip crit">{eur(-v)}</span>' if v > 20_000
                     else (f'<span class="chip warn">{eur(-v)}</span>' if v > 0.01
                           else '<span class="chip ok">al día</span>'))
            fil.append([esc(r["proveedor"]), eur(-r["pendiente_total"]), marca,
                        esc(r["tipologia"])] + [eur(-r[f"pago_{m}"]) for m in meses])
        t_pag = tabla(["Proveedor", "Pendiente", "Vencido", "Tipología"]
                      + [f"Pago {e}" for e in etiquetas], fil)
    else:
        g_pag, t_pag = '<p class="vacio">Sin datos.</p>', ""

    # ---- lo que Holded no sabe -------------------------------------------
    det = fc["detalle"]
    f_sal = [[esc(d["concepto"]), eur(d["importe"])] for d in det["salarios"]]
    f_sal.append(['<b>Total salarios</b>', f'<b>{eur(sum(d["importe"] for d in det["salarios"]))}</b>'])
    f_sl = [[esc(d["concepto"]), eur(d["importe"])] for d in det["cuotas_sl"]]
    f_sl.append(['<b>Total cuotas</b>', f'<b>{eur(sum(d["importe"] for d in det["cuotas_sl"]))}</b>'])
    t_sal = tabla(["Concepto", "Mensual"], f_sal)
    t_sl = tabla(["Operación", "Mensual"], f_sl)

    recu = fc["recurrentes"]
    if not recu.empty:
        piv = recu.pivot_table(index=["grupo", "proveedor"], columns="mes",
                               values="proyectado", aggfunc="sum").fillna(0)
        f_rec = []
        for (grp, pr), row in piv.iterrows():
            vals = [eur(row.get(m, 0)) for m in meses]
            if any(abs(row.get(m, 0)) > 0.01 for m in meses):
                f_rec.append([esc(pr), esc(grp)] + vals)
        t_rec = tabla(["Proveedor", "Grupo"] + etiquetas, f_rec) if f_rec else \
            '<p class="vacio">Todos los recurrentes ya tienen factura en Holded.</p>'
    else:
        t_rec = '<p class="vacio">Sin recurrentes configurados.</p>'

    rent = fc["rentings"]
    if not rent.empty:
        piv_r = rent.pivot_table(index="cliente", columns="mes", values="importe",
                                 aggfunc="sum").fillna(0)
        f_ren = [[esc(c)] + [eur(row.get(m, 0)) for m in meses]
                 for c, row in piv_r.iterrows()][:20]
        t_ren = tabla(["Cliente"] + etiquetas, f_ren)
    else:
        t_ren = '<p class="vacio">Sin cuotas de renting pendientes de facturar.</p>'

    # ---- cuadre -----------------------------------------------------------
    if cuadre["variacion_bancaria"] is None:
        cuadre_html = (
            f'<div class="nota-cuadre pendiente"><b>Cuadre no disponible todavía.</b> '
            f'{esc(cuadre["fuente"])}. En cuanto el extractor traiga los movimientos '
            f'de tesorería de Holded, este bloque compara automáticamente '
            f'cobros − pagos contra la variación de saldo.</div>'
            + tabla(["Concepto", cuadre["etiqueta"]], [
                ["Cobros ejecutados", eur(cuadre["cobros_ejecutados"])],
                ["Pagos ejecutados", eur(-cuadre["pagos_ejecutados"])],
                ["<b>Flujo según facturas</b>", f'<b>{eur(cuadre["flujo_por_facturas"])}</b>'],
                ["Variación de saldo bancario", "<i>pendiente de Holded</i>"],
                ["Diferencia", "<i>—</i>"],
            ]))
    else:
        residuo = cuadre.get("residuo")
        ok = residuo is not None and abs(residuo) <= cuadre["tolerancia"]
        titulo = "CUADRA" if ok else "QUEDA UN RESIDUO"
        cuadre_html = (
            f'<div class="nota-cuadre {"ok" if ok else "mal"}">'
            f'<b>{titulo}</b> — la diferencia entre facturas y banco es '
            f'{eur(cuadre["diferencia"])}, y {eur(cuadre.get("importe_sin_conciliar") or 0)} '
            f'se explican por movimientos que no pasan por factura. '
            f'Residuo sin explicar: <b>{eur(residuo)}</b> '
            f'(tolerancia {eur(cuadre["tolerancia"])}).</div>'
            + tabla(["Concepto", cuadre["etiqueta"]], [
                ["Cobros ejecutados", eur(cuadre["cobros_ejecutados"])],
                ["Pagos ejecutados", eur(-cuadre["pagos_ejecutados"])],
                ["<b>Flujo según facturas</b>", f'<b>{eur(cuadre["flujo_por_facturas"])}</b>'],
                ["Variación de saldo bancario", eur(cuadre["variacion_bancaria"])],
                ["Diferencia", eur(cuadre["diferencia"])],
                ["Movimientos sin factura", eur(cuadre.get("importe_sin_conciliar") or 0)],
                ["<b>Residuo sin explicar</b>", f'<b>{eur(residuo)}</b>'],
            ]))
        sc = cuadre.get("resumen_sin_conciliar") or []
        if sc:
            f_sc = [[esc(x["concepto"]), eur(x["importe"])] for x in sc[:25]]
            cuadre_html += (
                '<h2 style="font-size:15px;margin-top:22px">Qué hay detrás de la diferencia</h2>'
                '<p class="h2n">Movimientos bancarios del mes que no se corresponden con el '
                'cobro o el pago de ninguna factura: nóminas, impuestos, comisiones, '
                'pólizas, préstamos y traspasos entre cuentas propias.</p>'
                + tabla(["Concepto", "Importe"], f_sc))

    # ---- bancos -----------------------------------------------------------
    b = meta.get("bancos")
    NOM_TIPO = {"poliza": "Póliza", "tarjeta": "Tarjeta", "cuenta": "Cuenta"}
    if b is not None and not b.empty:
        # Las cuentas y tarjetas a cero no aportan nada y son mayoria: de 36
        # cuentas en Holded, casi todas estan a cero. Se dice cuantas se ocultan
        # para que nadie piense que falta una.
        ocultar = meta.get("ocultar_saldo_cero", True)
        vis = b[b["saldo"].abs() > 0.005] if ocultar else b
        n_cero = len(b) - len(vis)
        f_b = [[esc(r["cuenta"]), NOM_TIPO.get(r["tipo"], "Cuenta"), eur(r["saldo"])]
               for _, r in vis.iterrows()]
        t_ban = tabla(["Cuenta", "Tipo", "Saldo"], f_b) if f_b else \
            '<p class="vacio">Todas las cuentas a cero.</p>'
        av = meta.get("aviso_limites")
        if av:
            # Holded no publica limites de credito: el disponible sale de un
            # numero escrito a mano. Decir de donde viene es parte del dato.
            t_ban += f'<p class="vacio">{esc(av)}</p>'
        if n_cero:
            t_ban += (f'<p class="vacio">{n_cero} cuenta{"s" if n_cero != 1 else ""} '
                      f'a cero no se muestra{"n" if n_cero != 1 else ""}.</p>')
        if fc.get("deuda_tarjetas", 0) < -0.5:
            t_ban += (f'<p class="vacio">Las tarjetas suman '
                      f'{eur(fc["deuda_tarjetas"])} y no cuentan como caja: '
                      f'un saldo negativo en tarjeta es deuda a pagar.</p>')
    else:
        t_ban = '<p class="vacio">Sin cuentas.</p>'

    # ---- cobros y pagos YA REALIZADOS del mes -----------------------------
    # Sale de /payments, el libro de liquidaciones de Holded: cada apunte lleva
    # el documento al que va, asi que el desglose llega hasta la factura sin
    # deducirlo de la fecha de liquidacion, que solo guarda la del ultimo pago
    # y se lleva por delante los cobros parciales.
    def realizados_desplegable(rea, sentido):
        if rea is None or rea.empty:
            return ('<p class="vacio">Sin apuntes de liquidación en el mes. '
                    'Si esperabas verlos, revisa que el token tenga permiso '
                    'de lectura sobre pagos.</p>')
        f = rea[rea["sentido"] == sentido]
        if f.empty:
            return '<p class="vacio">Ninguno en el mes.</p>'
        grupos = []
        for terc, g in sorted(f.groupby("tercero"),
                              key=lambda kv: -abs(kv[1]["importe"].sum())):
            filas = [[esc(str(r["fecha"])), esc(r["num"]), esc(r["banco"]),
                      esc(r["concepto"]),
                      f'<span class="{"neg" if r["importe"] < 0 else ""}">'
                      f'{eur(r["importe"])}</span>']
                     for _, r in g.sort_values("fecha").iterrows()]
            grupos.append((terc, f'<b>{eur(g["importe"].sum())}</b>', filas))
        return detalle_desplegable(
            grupos, ["Fecha", "Factura", "Banco", "Concepto", "Importe"],
            alineacion=["", "", "", "", "r"])

    rea = meta.get("realizados")
    det_cob_hechos = realizados_desplegable(rea, "cobro")
    det_pag_hechos = realizados_desplegable(rea, "pago")
    det_sin_doc = realizados_desplegable(rea, "sin_documento")
    n_sin_doc = eje.get("n_sin_doc", 0)
    imp_sin_doc = eur(eje.get("importe_sin_doc", 0))
    etiqueta_m0 = m0["etiqueta"]
    tot_cob_hechos = eur(eje.get("cobros", 0))
    tot_pag_hechos = eur(eje.get("pagos_factura", 0))
    n_cob_hechos = eje.get("n_cobros", 0)
    n_pag_hechos = eje.get("n_pagos", 0)
    s_cob = "s" if n_cob_hechos != 1 else ""
    s_pag = "s" if n_pag_hechos != 1 else ""

    # Las partidas fijas del mes en curso: previsto, ya pagado y lo que queda.
    fij = fc.get("fijos_pagados") or {}
    NOM_FIJO = {"salarios": "Salarios y Seguridad Social",
                "cuotas_sl": "Cuotas S&amp;L y renting bancario",
                "recurrentes": "Gastos recurrentes",
                "otros_fijos": "Otros pagos fijos"}
    f_fij, det_fij = [], fij.get("_detalle") or {}
    for k, nom in NOM_FIJO.items():
        hecho = float(fij.get(k, 0) or 0)
        queda = abs(float(m0.get({"salarios": "salarios", "cuotas_sl": "cuotas_sl",
                                  "recurrentes": "recurrentes_proyectados",
                                  "otros_fijos": "otros_fijos"}[k], 0)))
        if hecho or queda:
            f_fij.append([nom, eur(hecho + queda), eur(-hecho), eur(-queda)])
    t_fijos = (tabla(["Partida", "Previsto del mes", "Ya pagado", "Queda por pagar"],
                     f_fij, alineacion=["", "r", "r", "r"])
               if f_fij else '<p class="vacio">Sin partidas fijas.</p>')

    f_fij_det = [[esc(str(x["fecha"])), esc(NOM_FIJO.get(k, k)), esc(x["concepto"]),
                  f'<span class="neg">{eur(x["importe"])}</span>']
                 for k, lista in det_fij.items() for x in lista]
    t_fijos_det = (tabla(["Fecha", "Partida", "Concepto en el banco", "Importe"],
                         sorted(f_fij_det), alineacion=["", "", "", "r"])
                   if f_fij_det else "")

    # ---- check contra contabilidad (430*) ---------------------------------
    ck = meta.get("check_clientes")
    if ck:
        f_ck = [["Saldo contable de las cuentas " + ", ".join(ck["prefijos"]) + "*",
                 eur(ck["contable"])],
                ["Exigible hoy (pendiente de cobro del panel)", eur(ck["exigible"])],
                ["Aplazado: cuotas que aún no han vencido", eur(ck["aplazado"])],
                ["Exigible + aplazado", f'<b>{eur(ck["suma"])}</b>'],
                ["Diferencia",
                 f'<span class="{"" if ck["cuadra"] else "neg"}">{eur(ck["diferencia"])}</span>']]
        cls_ck = ["", "", "", "sub", "total"]
        nota = ("cuadra" if ck["cuadra"] else
                f'no cuadra por {eur(abs(ck["diferencia"]))}')
        t_check = (f'<div class="nota-cuadre {"ok" if ck["cuadra"] else "mal"}">'
                   f'<b>{esc(nota.upper())}</b> — contabilidad lleva la factura entera '
                   f'mientras no se cobre; el panel solo llama exigible a la parte '
                   f'ya vencida según el calendario de Eli. La diferencia entre las '
                   f'dos cifras <em>es</em> lo aplazado, no un error '
                   f'(tolerancia {eur(ck["tolerancia"])}).</div>'
                   + tabla(["Concepto", "Importe"], f_ck,
                           alineacion=["", "r"], clases=cls_ck))
        det_ck = tabla(["Cuenta", "Nombre", "Saldo"],
                       [[esc(c["numero"]), esc(c["nombre"]), eur(c["saldo"])]
                        for c in ck["cuentas"]], alineacion=["", "", "r"])
        t_check += (f'<details><summary>Desglose por cuenta contable</summary>'
                    f'{det_ck}</details>')
    else:
        t_check = ('<p class="vacio">Sin plan contable. Requiere el permiso '
                   '<code>accounting:chart-of-accounts.read</code> en el token '
                   'de Holded.</p>')

    # ---- composicion de cada linea del forecast ---------------------------
    # El cuadro de arriba da los totales; aqui se abre cada linea y se ve de
    # que se compone, mes a mes. Sin esto hay que creerse un numero agregado.
    def _fila_meses(nombre, valores, negrita=False):
        cel = [f'<span class="{"neg" if v < 0 else ""}">{eur(v)}</span>'
               for v in valores]
        n = f"<b>{esc(nombre)}</b>" if negrita else esc(nombre)
        return [n] + cel

    def _desglose(titulo, filas, nota=""):
        if not filas:
            return ""
        tot = [sum(f[1][i] for f in filas) for i in range(len(meses))]
        cuerpo = [_fila_meses(n, v) for n, v in filas]
        cuerpo.append(_fila_meses("Total", tot, True))
        cl = [""] * (len(cuerpo) - 1) + ["sub"]
        return (f'<details><summary>{esc(titulo)}</summary>'
                + (f'<p class="h2n">{esc(nota)}</p>' if nota else "")
                + tabla(["Concepto"] + etiquetas, cuerpo,
                        alineacion=[""] + ["r"] * len(meses), clases=cl)
                + '</details>')

    des = []

    if not cli.empty:
        top = cli.reindex(cli[[f"teorico_{m}" for m in meses]].abs().sum(axis=1)
                          .sort_values(ascending=False).index).head(25)
        des.append(_desglose(
            f"Cobro de clientes — {len(cli)} cliente{'s' if len(cli) != 1 else ''}, se listan los 25 mayores",
            [(r["cliente"], [float(r[f"teorico_{m}"]) for m in meses])
             for _, r in top.iterrows()],
            "El resto está en la pestaña de Cobros, factura a factura."))

    rent = fc.get("rentings")
    if rent is not None and not rent.empty:
        for tipo, etiq in [("renting", "Rentings sin facturar"),
                           ("fusion", "Ventas financiadas desde LML (fusión)")]:
            g = rent[rent["tipo"] == tipo] if "tipo" in rent.columns else rent
            if g.empty:
                continue
            porcli = {}
            for _, r in g.iterrows():
                porcli.setdefault(r["cliente"], [0.0] * len(meses))
                if r["mes"] in meses:
                    porcli[r["cliente"]][meses.index(r["mes"])] += float(r["importe"])
            des.append(_desglose(f"{etiq} — por cliente",
                                 sorted(porcli.items(), key=lambda x: -sum(x[1]))))

    sf = (fc.get("detalle") or {}).get("sin_facturar") or []
    if sf:
        des.append(_desglose(
            "Ventas comprometidas sin facturar",
            [(f'{x["concepto"]} · {x["unidades"]} x {eur(x["precio"])} '
              f'+ {x["iva"]:.0%} IVA',
              [x["unidades"] * x["precio"] * (1 + x["iva"])] + [0.0] * (len(meses) - 1))
             for x in sf],
            "Solo cuentan en el mes en curso: es un compromiso, no un calendario."))

    aj = (fc.get("detalle") or {}).get("ajustes") or []
    if aj:
        des.append(_desglose(
            "Ajustes sobre cobros",
            [(x["concepto"], [float(x["importe"])] + [0.0] * (len(meses) - 1))
             for x in aj],
            "Criterio manual de config.yaml, no sale de Holded."))

    if not prov.empty:
        topp = prov.reindex(prov[[f"pago_{m}" for m in meses]].abs().sum(axis=1)
                            .sort_values(ascending=False).index).head(25)
        des.append(_desglose(
            f"Pago a proveedores — {len(prov)} proveedor{'es' if len(prov) != 1 else ''}, se listan los 25 mayores",
            [(r["proveedor"], [-abs(float(r[f"pago_{m}"])) for m in meses])
             for _, r in topp.iterrows()],
            "El mes en curso arrastra todo lo vencido. El resto está en la "
            "pestaña de Pagos."))

    recu = fc.get("recurrentes")
    if recu is not None and not recu.empty:
        col = "etiqueta" if "etiqueta" in recu.columns else recu.columns[0]
        porprov = {}
        for _, r in recu.iterrows():
            porprov.setdefault(r[col], [0.0] * len(meses))
            if r["mes"] in meses:
                porprov[r[col]][meses.index(r["mes"])] += float(r["proyectado"])
        des.append(_desglose(
            "Gastos recurrentes proyectados — por proveedor",
            sorted(porprov.items(), key=lambda x: sum(x[1])),
            "Solo se proyecta el mes que NO tiene factura en Holded: nunca se "
            "duplica con una factura real."))

    det = fc.get("detalle") or {}
    pag_fij = (det.get("fijos_pagados") or {})
    for clave, titulo in [("salarios", "Salarios y Seguridad Social"),
                          ("cuotas_sl", "Cuotas S&L y renting bancario"),
                          ("otros_fijos", "Otros pagos fijos")]:
        d0 = det.get(clave) or []
        if not d0:
            continue
        filas = [(x["concepto"], [float(x["importe"])] * len(meses)) for x in d0]
        hecho = float(pag_fij.get(clave, 0) or 0)
        if hecho:
            filas.append((f"Ya pagado en {m0['etiqueta']}",
                          [hecho] + [0.0] * (len(meses) - 1)))
        des.append(_desglose(
            f"{titulo} — composición mensual", filas,
            "No están en Holded: salen de config.yaml. En el mes en curso se "
            "descuenta lo ya pagado según el extracto." if hecho else
            "No están en Holded: salen de config.yaml."))

    t_desglose = ("".join(des) if des else
                  '<p class="vacio">Sin detalle disponible.</p>')

    # ---- caja del mes por naturaleza contable -----------------------------
    cn = meta.get("caja_naturaleza")
    if cn is not None and not cn.empty:
        f_cn = [[esc(r["naturaleza"]),
                 f'<span class="{"neg" if r["importe"] < 0 else ""}">{eur(r["importe"])}</span>',
                 f'{int(r["apuntes"])}'] for _, r in cn.iterrows()]
        f_cn.append(["<b>Variación de caja del mes</b>",
                     f'<b>{eur(float(cn["importe"].sum()))}</b>', ""])
        t_nat = tabla(["Contrapartida", "Importe", "Apuntes"], f_cn,
                      alineacion=["", "r", "r"],
                      clases=[""] * (len(f_cn) - 1) + ["total"])
    else:
        t_nat = ('<p class="vacio">Sin libro diario. Requiere el permiso '
                 '<code>accounting:daily-ledger.read</code> en el token.</p>')

    # ---- puente hasta el unlevered ejecutado ------------------------------
    if eje.get("fuente") == "libro diario":
        f_pu = []
        if abs(eje.get("traspasos", 0)) > 0.5:
            f_pu.append([
                "<i>Traspasos entre cuentas propias, ya excluidos: "
                "la misma caja cambiada de sitio</i>",
                f'<i>{eur(eje["traspasos"])}</i>'])
        f_pu.append(["Variación real de caja del mes",
                     eur(eje["variacion_caja"])])
        for x in eje.get("detalle_financiacion") or []:
            # el nombre real de la cuenta, no solo el grupo del PGC: "52000042"
            # dice "Deudas a corto con entidades de credito" y en realidad es
            # la tarjeta American Express. Sin el nombre no hay criterio que
            # discutir.
            nom = x.get("nombre") or x["concepto"]
            f_pu.append([f"&nbsp;&nbsp;<code>{esc(x.get('cuenta',''))}</code> "
                         f"{esc(nom)}",
                         f'<span class="{"neg" if x["importe"] < 0 else ""}">'
                         f'{eur(x["importe"])}</span>'])
        f_pu += [["Financiación incluida en esa variación",
                  f'<span class="{"neg" if eje["financiacion"] < 0 else ""}">'
                  f'{eur(eje["financiacion"])}</span>']]
        tras = eje.get("traspasos", 0)
        apl = eje.get("por_aplicar", eje.get("suspenso", 0))
        if abs(apl) > 0.5:
            f_pu.append([
                "Pendiente de aplicar de verdad — <b>hay que clasificarlo</b>",
                f'<span class="{"neg" if apl < 0 else ""}">{eur(apl)}</span>'])
        f_pu += [["<b>Unlevered FCF ejecutado</b> = variación − financiación"
                  + (" − pendiente de aplicar"
                     if abs(eje.get("por_aplicar", 0)) > 0.5 else ""),
                  f'<b>{eur(eje["fcf"])}</b>'],
                 ["Para contrastar: la misma cifra contando solo facturas",
                  eur(eje.get("por_facturas", 0))]]
        n_sub = 1 + (abs(eje.get("por_aplicar", 0)) > 0.5)
        cl_pu = [""] * (len(f_pu) - 2 - n_sub) + ["sub"] * n_sub + ["total", ""]
        t_puente = tabla(["Concepto", "Importe"], f_pu,
                         alineacion=["", "r"], clases=cl_pu)
        # Lo que se ha quedado fuera del perimetro, por si falta alguna cuenta
        # que si deberia estar. Donde se pone esa frontera mueve la cifra
        # entera, asi que se ensena en vez de darla por buena.
        # Los 131.119 de la 555, apunte a apunte: es lo que hay que clasificar
        ds = eje.get("detalle_suspenso") or []
        if ds:
            t_puente += (
                f'<details open><summary>Las cuentas puente de {etiqueta_m0}, '
                f'apunte a apunte — {len(ds)} movimiento'
                f'{"s" if len(ds) != 1 else ""}</summary>'
                + tabla(["Fecha", "Qué es", "Cuenta", "Concepto en el banco",
                         "Importe"],
                        [[esc(x["fecha"]),
                          ('<span class="chip ok">traspaso</span>'
                           if x.get("traspaso") else
                           '<span class="chip warn">por aplicar</span>'),
                          f'<code>{esc(x["cuenta"])}</code> {esc(x["nombre"])}',
                          esc(x["concepto"]),
                          f'<span class="{"neg" if x["importe"] < 0 else ""}">'
                          f'{eur(x["importe"])}</span>'] for x in ds],
                        alineacion=["", "", "", "", "r"])
                + '</details>')

        fp = eje.get("fuera_perimetro") or []
        if fp:
            t_puente += (
                '<details><summary>Qué se ha quedado fuera del perímetro de '
                'financiación (mayores movimientos)</summary>'
                + tabla(["Cuenta", "Nombre", "Importe"],
                        [[f'<code>{esc(x["cuenta"])}</code>',
                          esc(x.get("nombre") or x["concepto"]),
                          f'<span class="{"neg" if x["importe"] < 0 else ""}">'
                          f'{eur(x["importe"])}</span>'] for x in fp],
                        alineacion=["", "", "r"])
                + '</details>')
    else:
        t_puente = ('<p class="vacio">Sin libro diario: el ejecutado se calcula '
                    'con facturas y extracto, que no ve los pagos sin factura '
                    '(impuestos, comisiones). Requiere el permiso '
                    '<code>accounting:daily-ledger.read</code>.</p>')

    # ---- serie de unlevered ejecutado -------------------------------------
    su = meta.get("serie_unlevered") or []
    if su:
        f_su = [[esc(x["etiqueta"]), eur(x["variacion_caja"]),
                 f'<span class="{"neg" if x["financiacion"] < 0 else ""}">'
                 f'{eur(x["financiacion"])}</span>',
                 f'<b><span class="{"neg" if x["unlevered"] < 0 else ""}">'
                 f'{eur(x["unlevered"])}</span></b>'] for x in su]
        t_serie = tabla(["Mes", "Variación de caja", "Financiación",
                         "Unlevered ejecutado"], f_su,
                        alineacion=["", "r", "r", "r"])
    else:
        t_serie = ('<p class="vacio">Sin libro diario para meses anteriores.</p>')

    # ---- avisos de calidad del dato ---------------------------------------
    dq = meta.get("calidad", [])
    dq_html = ("<ul class='dq'>" + "".join(f"<li>{d}</li>" for d in dq) + "</ul>") \
        if dq else '<p class="vacio">Sin incidencias.</p>'


    # ---- KPIs de las pestanas de cobros y pagos --------------------------
    n_cli = int((cli["pendiente_cobro"].abs() > 0.01).sum()) if not cli.empty else 0
    cob_mes = float(cli["cuota_mes"].sum()) if not cli.empty else 0.0
    top_cli = (cli.iloc[0]["cliente"], cli.iloc[0]["pendiente_cobro"]) if not cli.empty else ("—", 0)
    kpis_cob = "".join([
        kpi("Pendiente de cobro exigible", eur(pend_cobro), f"{n_cli} clientes"),
        kpi("En retraso", eur(retraso),
            f"{retraso / pend_cobro:.0%} del exigible" if pend_cobro else "—",
            "aviso" if retraso > 300_000 else ""),
        kpi(f"Cuota teórica de {m0['etiqueta']}", eur(cob_mes), "según calendario de Eli"),
        kpi("Mayor riesgo", eur(top_cli[1]), esc(top_cli[0])[:34]),
    ])

    n_prov = int((prov["pendiente_total"].abs() > 0.01).sum()) if not prov.empty else 0
    n_venc = int((prov["vencido"] > 0.01).sum()) if not prov.empty else 0
    pend_prov = float(prov["pendiente_total"].sum()) if not prov.empty else 0.0
    no_holded = m0["salarios"] + m0["cuotas_sl"] + m0["recurrentes_proyectados"] + m0["otros_fijos"]
    kpis_pag = "".join([
        kpi("Pendiente a proveedores", eur(-pend_prov), f"{n_prov} proveedores"),
        kpi("Vencido y sin pagar", eur(-vencido), f"{n_venc} proveedores",
            "aviso" if vencido > 200_000 else ""),
        kpi(f"Pago previsto {m0['etiqueta']}", eur(m0["pago_proveedores"]),
            "vencimientos hasta fin de mes"),
        kpi("Fuera de Holded", eur(no_holded),
            "salarios, cuotas S&L y recurrentes"),
    ])

    # ---- detalle factura a factura ---------------------------------------
    dc = fc.get("detalle_cobros")
    grupos_cob = []
    if dc is not None and not dc.empty:
        act = dc[(dc["pendiente_cobro"].abs() > 0.01) |
                 (dc[[f"teorico_{m}" for m in meses[1:]]].abs().sum(axis=1) > 0.01)]
        for cliente, g in act.groupby("cliente"):
            g = g.sort_values("pendiente_cobro", ascending=False)
            pend, ret = g["pendiente_cobro"].sum(), g["retraso"].sum()
            resumen = (f'<b>{eur(pend)}</b> exigible'
                       + (f' · <span class="rojo">{eur(ret)} en retraso</span>' if ret > 0.01 else ''))
            filas = [[esc(r["num"]), esc(r["cuenta"])[:42],
                      esc(r["vencimiento"] or "—"), eur(r["total"]),
                      eur(r["teorico_hoy"]), eur(r["liquidado"]),
                      eur(r["pendiente_cobro"]),
                      (f'<span class="chip crit">{eur(r["retraso"])}</span>' if r["retraso"] > 0.01
                       else '<span class="chip ok">al día</span>')]
                     + [eur(r[f"teorico_{m}"]) for m in meses[1:]]
                     for _, r in g.iterrows()]
            grupos_cob.append((cliente, resumen, filas))
        grupos_cob.sort(key=lambda x: -sum(float(str(f[6]).replace(" ", "").replace("€", "").replace("—", "0") or 0)
                                           for f in x[2]) if False else 0)
        grupos_cob = sorted(
            grupos_cob,
            key=lambda x: -act[act["cliente"] == x[0]]["pendiente_cobro"].sum())
    cab_cob = (["Factura", "Concepto", "Vencimiento", "Importe", "Teórico hoy",
                "Cobrado", "Exigible", "Retraso"] + [f"Teórico {e}" for e in etiquetas[1:]])
    det_cobros = detalle_desplegable(grupos_cob, cab_cob,
                                     vacio="Sin cobros pendientes.")

    dp = fc.get("detalle_pagos")
    grupos_pag = []
    if dp is not None and not dp.empty:
        for prov_nom, g in dp.groupby("proveedor"):
            g = g.sort_values("vencimiento")
            pend = g["pendiente"].sum()
            venc = g[g["vencido"]]["pendiente"].sum()
            resumen = (f'<b>{eur(-pend)}</b> pendiente'
                       + (f' · <span class="rojo">{eur(-venc)} vencido</span>' if venc > 0.01 else ''))
            filas = [[esc(r["num"]), esc(r["cuenta"])[:42],
                      esc(r["vencimiento"] or "—"), esc(r["tipologia"]),
                      eur(-r["total"]), eur(-r["liquidado"]), eur(-r["pendiente"]),
                      (f'<span class="chip crit">vencido</span>' if r["vencido"]
                       else f'<span class="chip ok">{esc(r["estado"])}</span>')]
                     for _, r in g.iterrows()]
            grupos_pag.append((prov_nom, resumen, filas))
        grupos_pag = sorted(grupos_pag,
                            key=lambda x: -dp[dp["proveedor"] == x[0]]["pendiente"].sum())
    cab_pag = ["Factura", "Concepto", "Vencimiento", "Tipología",
               "Importe", "Pagado", "Pendiente", "Estado"]
    det_pagos = detalle_desplegable(grupos_pag, cab_pag,
                                    vacio="Sin pagos pendientes.")

    cuadre_proy = bloque_cuadre_proyeccion(meta.get("cuadre_proyeccion") or [], etiquetas)
    # Aviso a toda pantalla si los datos de origen no son creibles. Un fallo
    # silencioso de Holded produciria un forecast con pinta de correcto, y eso
    # es peor que no tener dashboard.
    problemas = meta.get("problemas_graves") or []
    if problemas:
        banner = ('<div class="banner"><b>ATENCION: los datos de origen no son '
                  'fiables.</b><ul>' +
                  "".join(f"<li>{esc(p)}</li>" for p in problemas) +
                  '</ul><span>No tomes decisiones de pago con estas cifras hasta '
                  'revisar el log del workflow.</span></div>')
    else:
        banner = ""

    url_workflow = meta.get("url_workflow") or (
        "https://github.com/alejandrovicente97/leaseir-control-caja"
        "/actions/workflows/caja.yml")

    # ---- contraste con el Excel ------------------------------------------
    ce = meta.get("contraste") or {}
    if ce.get("activo"):
        pares = [("Cobro de clientes", m0["cobro_clientes"], ce.get("cobro_clientes")),
                 ("Rentings sin facturar", m0["rentings_sin_factura"], ce.get("rentings_ajuste")),
                 ("Cash in", m0["cash_in"], ce.get("cash_in")),
                 ("Pago a proveedores", m0["pago_proveedores"],
                  (ce.get("pago_proveedores") or 0) + (ce.get("proveedores_variable") or 0)),
                 ("Salarios", m0["salarios"], ce.get("salarios")),
                 ("Cuotas S&L", m0["cuotas_sl"], ce.get("cuotas_sl")),
                 ("Cash out", m0["cash_out"], ce.get("cash_out")),
                 ("Unlevered FCF", m0["fcf"], ce.get("fcf"))]
        f_ce, cl_ce = [], []
        for nom, mot, exc in pares:
            if exc is None:
                continue
            dif = mot - exc
            chip = ("ok" if abs(dif) < 5000 else ("warn" if abs(dif) < 100000 else "crit"))
            f_ce.append([f"<b>{esc(nom)}</b>" if "Cash" in nom or "FCF" in nom else esc(nom),
                         eur(mot), eur(exc),
                         f'<span class="chip {chip}">{eur(dif)}</span>'])
            cl_ce.append("sub" if ("Cash" in nom or "FCF" in nom) else "")
        t_ce = tabla(["Concepto", "Motor", f"Excel {esc(ce.get('fichero',''))}", "Diferencia"],
                     f_ce, clases=cl_ce)
        ad = ce.get("adicionales_manuales") or []
        if ad:
            f_ad = [[esc(a["concepto"]), eur(a["importe"])] for a in ad]
            f_ad.append(["<b>Total a trasladar a config</b>",
                         f'<b>{eur(sum(a["importe"] for a in ad))}</b>'])
            t_ad = tabla(["Partida manual del Excel", "Importe"], f_ad)
        else:
            t_ad = ""
        contraste_html = f"""
<section>
  <h2>Contraste con tu Excel</h2>
  <p class="h2n">Puente entre lo que calcula el motor y lo que tenias a mano en
   {esc(ce.get('fichero',''))}. Las diferencias no son errores: son criterios
   distintos, y aqui quedan explicitos.</p>
  {t_ce}
  <h2 style="font-size:15px;margin-top:22px">Lo que en tu Excel metias a mano</h2>
  <p class="h2n">El motor no puede adivinar tu criterio comercial. Estas partidas
   van en <code>config.yaml</code> &rarr; <code>cobros.ajustes_positivos</code>
   y entonces el forecast las recoge sola.</p>
  {t_ad}
</section>"""
    else:
        contraste_html = ""

    # ---- HTML -------------------------------------------------------------
    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Leaseir · Control de caja y forecast</title>
<style>
*{{box-sizing:border-box}}
body{{margin:0;background:{P['plane']};color:{P['ink']};
 font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
 -webkit-font-smoothing:antialiased}}
.wrap{{max-width:1220px;margin:0 auto;padding:0 20px 72px}}
.marca{{background:{P['brand']};margin:0 -20px 0;padding:22px 20px}}
.marca-in{{max-width:1220px;margin:0 auto;display:flex;justify-content:space-between;
 align-items:flex-end;gap:24px;flex-wrap:wrap}}
.wordmark{{display:block;color:#fff;font-size:27px;font-weight:300;letter-spacing:7px}}
.claim{{display:block;color:#a9c4ce;font-size:10.5px;letter-spacing:3.1px;
 text-transform:uppercase;margin-top:3px}}
.marca-meta{{text-align:right}}
.doc{{color:#fff;font-size:16px;font-weight:500;letter-spacing:-.1px}}
.doc2{{color:#a9c4ce;font-size:12px;margin-top:2px}}
.tira{{background:{P['brand2']};margin:0 -20px 26px;padding:9px 20px;
 display:flex;gap:26px;flex-wrap:wrap;justify-content:center;
 font-size:12.5px;color:#cfe0e6}}
.tira b{{color:#fff;font-weight:600}}
.tira i{{font-style:normal;opacity:.65}}
.btn-refresh{{background:rgba(255,255,255,.14);color:#fff;text-decoration:none;
 padding:4px 13px;border-radius:4px;font-weight:600;font-size:12.5px;
 border:1px solid rgba(255,255,255,.28);transition:background .12s;white-space:nowrap}}
.btn-refresh:hover{{background:rgba(255,255,255,.26)}}
h1{{font-size:27px;margin:0 0 4px;letter-spacing:-.4px}}
h2{{font-size:17px;margin:0 0 4px;letter-spacing:-.2px;color:{P['brand']}}}
.h2n{{color:{P['muted']};font-size:13px;margin:0 0 14px}}
section{{background:{P['surface']};border:1px solid {P['border']};border-radius:4px;
 padding:22px 24px;margin-bottom:18px;box-shadow:0 1px 2px rgba(31,77,92,.05)}}
section>h2:first-child{{padding-bottom:9px;border-bottom:2px solid {P['brand']};
 display:inline-block;margin-bottom:8px}}
.kpis{{margin-top:0;display:grid;grid-template-columns:repeat(auto-fit,minmax(196px,1fr));gap:12px;margin-bottom:20px}}
.kpi{{background:{P['surface']};border:1px solid {P['border']};border-radius:4px;
 padding:15px 16px;border-top:3px solid {P['brand']};box-shadow:0 1px 2px rgba(31,77,92,.05)}}
.kpi.ok{{border-top-color:{P['good']}}}
.kpi.aviso{{border-top-color:{P['warn']}}}
.kpi.mal{{border-top-color:{P['crit']}}}
.k-t{{font-size:11.5px;text-transform:uppercase;letter-spacing:.5px;color:{P['muted']};
 font-weight:600;margin-bottom:6px}}
.k-v{{font-size:23px;font-weight:650;letter-spacing:-.6px;font-variant-numeric:tabular-nums;
 color:{P['brand']}}}
.k-n{{font-size:12px;color:{P['ink2']};margin-top:4px}}
table{{width:100%;border-collapse:collapse;font-size:13.5px;font-variant-numeric:tabular-nums}}
th{{text-align:left;font-size:10.5px;text-transform:uppercase;letter-spacing:.5px;
 color:{P['brand']};font-weight:700;padding:8px 10px;
 border-bottom:1.5px solid {P['brand']};white-space:nowrap}}
td{{padding:7px 10px;border-bottom:1px solid {P['grid']}}}
th.r,td.r{{text-align:right}}
tr.sub td{{background:#f1f4f5;font-weight:600}}
tr.total td{{background:{P['brand']};color:#fff;font-weight:700}}
tr.total td .neg{{color:#ffc9c9}}
tbody tr:hover td{{background:#f7f9fa}}
tr.sub:hover td,tr.total:hover td{{background:inherit}}
.b{{font-weight:650}} .neg{{color:{P['crit']}}}
.chip{{display:inline-block;padding:1px 8px;border-radius:20px;font-size:12px;font-weight:600}}
.chip.ok{{background:#e6f5e6;color:{P['up']}}}
.chip.warn{{background:#fdf1d8;color:#8a5d00}}
.chip.crit{{background:#fbe6e6;color:#a32020}}
.alertas{{list-style:none;margin:0;padding:0}}
.alertas li{{padding:9px 12px;border-radius:9px;margin-bottom:7px;font-size:14px;
 display:flex;gap:9px;align-items:flex-start}}
.alertas li.critico{{background:#fbe6e6;color:#8f1d1d}}
.alertas li.aviso{{background:#fdf4e2;color:#7a5200}}
.ico{{font-size:11px;line-height:20px}}
.chart{{display:block;margin:6px 0 4px;overflow:visible}}
.lbl{{font-size:11.5px;fill:{P['ink2']}}}
.val{{font-size:11.5px;fill:{P['ink']};font-weight:600;font-variant-numeric:tabular-nums}}
.ax{{font-size:11px;fill:{P['muted']}}}
.leyenda{{display:flex;gap:16px;flex-wrap:wrap;margin:2px 0 10px}}
.li{{display:flex;align-items:center;gap:6px;font-size:12.5px;color:{P['ink2']}}}
.li i{{width:11px;height:11px;border-radius:3px;display:inline-block}}
.vacio{{color:{P['muted']};font-size:13.5px;font-style:italic;margin:6px 0}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}
@media(max-width:860px){{.grid2{{grid-template-columns:1fr}}}}
.nota-cuadre{{padding:12px 14px;border-radius:10px;font-size:13.5px;margin-bottom:14px;line-height:1.5}}
.nota-cuadre.ok{{background:#e6f5e6;color:#0d5c0d}}
.nota-cuadre.mal{{background:#fbe6e6;color:#8f1d1d}}
.nota-cuadre.pendiente{{background:#f0f2f5;color:{P['ink2']}}}
.dq{{margin:0;padding-left:20px;font-size:13.5px;color:{P['ink2']}}}
.dq li{{margin-bottom:6px}}
details{{margin-top:12px}}
summary{{cursor:pointer;font-size:13px;color:{P['ink2']};font-weight:600;padding:6px 0}}
.banner{{background:#fbe6e6;border-left:4px solid {P['crit']};border-radius:4px;
 padding:14px 18px;margin:0 0 18px;color:#8f1d1d;font-size:14px}}
.banner b{{display:block;margin-bottom:6px;font-size:15px}}
.banner ul{{margin:6px 0;padding-left:22px}}
.banner span{{display:block;margin-top:8px;font-weight:600}}
.tabs{{display:flex;gap:6px;margin:0 0 20px;border-bottom:2px solid {P['grid']}}}
.tab{{appearance:none;background:none;border:0;border-bottom:3px solid transparent;
 margin-bottom:-2px;padding:11px 18px;font-size:14.5px;font-weight:600;
 color:{P['muted']};cursor:pointer;font-family:inherit;transition:color .12s}}
.tab:hover{{color:{P['ink2']}}}
.tab.activa{{color:{P['brand']};border-bottom-color:{P['brand']}}}
.panel{{display:none}}
.panel.visible{{display:block}}
.buscador{{margin:16px 0 10px}}
.buscador input{{width:100%;max-width:340px;padding:8px 12px;font-size:14px;
 font-family:inherit;border:1px solid {P['axis']};border-radius:4px;
 background:{P['surface']};color:{P['ink']}}}
.buscador input:focus{{outline:2px solid {P['brand3']};outline-offset:-1px}}
.detalles{{border-top:1px solid {P['grid']}}}
details.terc{{border-bottom:1px solid {P['grid']};margin:0}}
details.terc>summary{{display:flex;align-items:center;gap:12px;padding:7px 6px;
 cursor:pointer;font-size:12.5px;list-style:none}}
details.terc>summary::-webkit-details-marker{{display:none}}
details.terc>summary::before{{content:"▸";color:{P['muted']};font-size:11px;
 width:12px;flex:none;transition:transform .12s}}
details.terc[open]>summary::before{{transform:rotate(90deg)}}
details.terc>summary:hover{{background:#f7f9fa}}
details.terc[open]>summary{{background:#f1f4f5;font-weight:600}}
.t-nom{{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.t-res{{color:{P['ink2']};font-size:12px;white-space:nowrap;font-variant-numeric:tabular-nums}}
.t-n{{color:{P['muted']};font-size:11px;width:58px;text-align:right;flex:none}}
.t-body{{padding:2px 6px 12px;overflow-x:auto}}
.t-body table{{font-size:11.5px}}
.t-body td{{padding:4px 8px}}
.t-body th{{padding:5px 8px}}
.rojo{{color:{P['crit']}}}
.pie{{margin:30px -20px -72px;padding:20px;background:{P['brand']};color:#a9c4ce;
 font-size:11.5px;line-height:1.65;display:flex;justify-content:space-between;
 gap:24px;flex-wrap:wrap}}
.pie b{{color:#fff;letter-spacing:1.5px}}
.pie-r{{max-width:660px;text-align:right}}
code{{background:#eef1f2;padding:1px 5px;border-radius:3px;font-size:12.5px}}
</style></head>
<body><div class="wrap">

<header class="marca">
  <div class="marca-in">
    <div class="logo">
      <span class="wordmark">LEASEIR</span>
      <span class="claim">Aesthetic Intelligence</span>
    </div>
    <div class="marca-meta">
      <div class="doc">Control de caja y forecast de tesorería</div>
      <div class="doc2">Dirección Financiera · Leaseir Technologies S.L.U.</div>
    </div>
  </div>
</header>

<div class="tira">
  <span>Mes en curso <b>{esc(m0['etiqueta'])}</b></span>
  <span>Horizonte <b>{esc(etiquetas[-1])}</b></span>
  <span>Fuente <b>{esc(meta.get('origen', '—'))}</b></span>
  <span>Actualizado <b>{ahora_es():%d/%m/%Y · %H:%M} h</b> <i>(hora peninsular)</i></span>
  <a class="btn-refresh" href="{url_workflow}" target="_blank" rel="noopener"
     title="Abre GitHub Actions y lanza el workflow: vuelve a leer Holded y el calendario de Eli">
     ⟳ Forzar actualización</a>
</div>

{banner}

<nav class="tabs">
  <button class="tab activa" data-p="p1">Forecast de caja</button>
  <button class="tab" data-p="p2">Cobros</button>
  <button class="tab" data-p="p3">Pagos</button>
</nav>

<div id="p1" class="panel visible">

  <div class="kpis">{kpis}</div>

  <section>
    <h2>Evolución de la caja</h2>
    <p class="h2n">Saldo de partida, flujo libre de cada mes y saldo al final del horizonte.</p>
    {wf}
  </section>

  <section>
    <h2>Forecast de caja</h2>
    <p class="h2n">Cobros y pagos por mes. Los pagos a proveedor arrastran los vencidos
     al mes en curso; las partidas que no están en Holded (salarios, cuotas de banco,
     recurrentes) se proyectan aparte.</p>
    {tabla_fc}
    <div style="margin-top:18px">{lg_mes}{barras_mes}</div>
  </section>

  <section>
    <h2>De qué se compone cada línea</h2>
    <p class="h2n">Los mismos importes del cuadro de arriba, abiertos. Cada
     bloque suma exactamente la línea que le corresponde.</p>
    {t_desglose}
  </section>

  <section>
    <h2>Check de caja</h2>
    <p class="h2n">Saldo inicial + cash in + cash out = saldo final. Cada mes se
     calcula por separado y se compara: si algo no cuadrase, sería un error del motor,
     no una diferencia de criterio.</p>
    {cuadre_proy}
    <h2 style="font-size:15px;margin-top:24px">Cuadre contra el banco</h2>
    <p class="h2n">Lo ejecutado del mes contra la variación real de saldo.</p>
    {cuadre_html}
  </section>

  <section>
    <h2>Cómo se llega al unlevered ejecutado de {etiqueta_m0}</h2>
    <p class="h2n">Igual que en el bottom-up: de la variación real de caja hacia
     arriba, quitando lo que es financiación. La cuenta por facturas se queda
     como desglose, pero no como cifra: solo ve los pagos que llevan factura.</p>
    {t_puente}
  </section>

  <section>
    <h2>Unlevered ejecutado de los meses cerrados</h2>
    <p class="h2n">La misma cuenta, mes a mes. Para contrastarlo contra el
     bottom-up sin discutir una sola cifra: si la diferencia se repite todos los
     meses es un criterio distinto; si sale en uno solo, es un apunte.</p>
    {t_serie}
  </section>

  <section>
    <h2>Caja de {etiqueta_m0} por naturaleza contable</h2>
    <p class="h2n">De qué se compone el movimiento de caja del mes, según la
     contrapartida de cada asiento en el libro diario. Es lo que convierte una
     línea de extracto en un concepto: contra 430 es cobro de cliente, contra
     640 una nómina, contra 520 amortización de deuda.</p>
    {t_nat}
  </section>

  <section>
    <h2>Posición bancaria</h2>
    {t_ban}
  </section>

  {contraste_html}

  <section>
    <h2>Calidad del dato</h2>
    <p class="h2n">Incidencias detectadas al construir el forecast.</p>
    {dq_html}
  </section>

</div>

<div id="p2" class="panel">

  <div class="kpis">{kpis_cob}</div>

  <section>
    <h2>Pendiente de cobro por cliente</h2>
    <p class="h2n">Exigible = cuota teórica acumulada del calendario de Eli menos lo
     realmente cobrado. De un renting a 36 meses solo cuenta lo ya vencido.</p>
    {g_cob}
  </section>

  <section>
    <h2>Cobros ya realizados en {etiqueta_m0}</h2>
    <p class="h2n">Lo que ha entrado de verdad entre el día 1 y hoy, apunte a
     apunte y ligado a su factura. Total {tot_cob_hechos} en {n_cob_hechos} apunte{s_cob}.</p>
    <div class="buscador">
      <input type="text" id="bch" placeholder="Filtrar cliente…" oninput="filtrar('p2h', this.value)">
    </div>
    <div id="p2h" class="detalles">{det_cob_hechos}</div>
  </section>

  <section>
    <h2>Detalle factura a factura</h2>
    <p class="h2n">Despliega cada cliente para ver sus facturas: importe, cuánto
     debería estar cobrado a día de hoy, cuánto se ha cobrado y qué queda.</p>
    <div class="buscador">
      <input type="text" id="bc" placeholder="Filtrar cliente…" oninput="filtrar('p2c', this.value)">
    </div>
    <div id="p2c" class="detalles">{det_cobros}</div>
  </section>

  <section>
    <h2>Check contra contabilidad: cuentas de clientes</h2>
    <p class="h2n">El puente entre lo que dice el mayor y lo que dice el panel.
     Si cuadra, el calendario de Eli está bien cargado.</p>
    {t_check}
  </section>

  <section>
    <h2>Cuotas de renting pendientes de facturar</h2>
    <p class="h2n">Están en el calendario de Eli y todavía no tienen factura emitida
     en Holded. Entran en el forecast aunque Holded no las conozca.</p>
    {t_ren}
  </section>

</div>

<div id="p3" class="panel">

  <div class="kpis">{kpis_pag}</div>

  <section>
    <h2>Pendiente de pago por proveedor</h2>
    <p class="h2n">El forecast de cada mes recoge todo lo pendiente con vencimiento
     hasta fin de ese mes, así que los vencidos se arrastran al mes en curso.</p>
    {g_pag}
  </section>

  <section>
    <h2>Pagos ya realizados en {etiqueta_m0}</h2>
    <p class="h2n">Lo que ha salido de verdad entre el día 1 y hoy, apunte a apunte
     y ligado a su factura. Total {tot_pag_hechos} en {n_pag_hechos} apunte{s_pag}.</p>
    <div class="buscador">
      <input type="text" id="bph" placeholder="Filtrar proveedor…" oninput="filtrar('p3h', this.value)">
    </div>
    <div id="p3h" class="detalles">{det_pag_hechos}</div>
  </section>

  <section>
    <h2>Apuntes de {etiqueta_m0} sin documento asociado</h2>
    <p class="h2n">{n_sin_doc} apuntes por {imp_sin_doc} en total que no van
     ligados a ninguna factura: cuotas de tarjeta, peajes, impuestos, traspasos.
     Holded manda el importe siempre en positivo, así que sin documento detrás
     <b>no se puede saber el signo</b> y no se suman a cobros ni a pagos. El
     unlevered ejecutado sí los recoge, porque sale de la caja real.</p>
    <div class="buscador">
      <input type="text" id="bsd" placeholder="Filtrar…" oninput="filtrar('psd', this.value)">
    </div>
    <div id="psd" class="detalles">{det_sin_doc}</div>
  </section>

  <section>
    <h2>Partidas fijas de {etiqueta_m0}: lo pagado y lo que queda</h2>
    <p class="h2n">Las nóminas y las cuotas de S&amp;L no salen todas el mismo día.
     Lo ya pagado está descontado del saldo de hoy, así que el forecast del mes
     solo proyecta la parte que falta: si no, se contaría dos veces.</p>
    {t_fijos}
    {t_fijos_det}
  </section>

  <section>
    <h2>Detalle factura a factura</h2>
    <p class="h2n">Despliega cada proveedor para ver factura, concepto, vencimiento
     y estado.</p>
    <div class="buscador">
      <input type="text" id="bp" placeholder="Filtrar proveedor…" oninput="filtrar('p3p', this.value)">
    </div>
    <div id="p3p" class="detalles">{det_pagos}</div>
  </section>

  <section>
    <h2>Pagos que no están en Holded</h2>
    <p class="h2n">No existen como factura y sin embargo hay que pagarlos. Es la
     razón principal por la que el forecast de Holded se queda corto.</p>
    <div class="grid2">
      <div><h2 style="font-size:15px">Salarios y Seguridad Social</h2>{t_sal}</div>
      <div><h2 style="font-size:15px">Cuotas S&amp;L y renting bancario</h2>{t_sl}</div>
    </div>
    <h2 style="font-size:15px;margin-top:22px">Gastos recurrentes proyectados</h2>
    <p class="h2n">Solo se proyectan los meses en los que aún no hay factura en Holded,
     así que nunca se duplica.</p>
    {t_rec}
  </section>

</div>

<footer class="pie">
  <div class="pie-l"><b>LEASEIR TECHNOLOGIES S.L.U.</b> · leaseir.com</div>
  <div class="pie-r">Documento interno de la Dirección Financiera.
   Generado automáticamente a partir de Holded y del calendario de cobros.
   No difundir fuera del Comité de Dirección.</div>
</footer>
</div>

<script>
document.querySelectorAll('.tab').forEach(function (b) {{
  b.addEventListener('click', function () {{
    document.querySelectorAll('.tab').forEach(function (x) {{ x.classList.remove('activa'); }});
    document.querySelectorAll('.panel').forEach(function (x) {{ x.classList.remove('visible'); }});
    b.classList.add('activa');
    document.getElementById(b.dataset.p).classList.add('visible');
    window.scrollTo({{ top: 0, behavior: 'smooth' }});
  }});
}});

function filtrar(id, q) {{
  var t = (q || '').toLowerCase();
  document.getElementById(id).querySelectorAll('details.terc').forEach(function (d) {{
    var n = d.querySelector('.t-nom').textContent.toLowerCase();
    d.style.display = n.indexOf(t) === -1 ? 'none' : '';
  }});
}}
</script>
</body></html>"""
