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

import calendar as _callib
import html
import json
import os
import re

from fuentes import nombre_mes
from datetime import date, datetime, timezone

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


def pantalla_nacho(rn, fc, meta):
    """
    LA PANTALLA DE LA REUNION. Una pregunta arriba, cinco cifras debajo, y
    los graficos que las sostienen. Cabe entera en un portatil: nada de
    scroll, porque en una pantalla compartida el scroll es donde se pierde
    la conversacion. Todo el detalle vive en ventanas que se abren encima.
    """
    if not rn:
        return ""
    col = float(rn["colchon"])
    ok = rn["llega"] and rn["cierre_mes"] >= col

    def cifra(v):
        return f'<span class="{"neg" if v < 0 else ""}">{eur(v)}</span>'

    # --- la respuesta, sin banda ----------------------------------------
    # Alejandro: "esto lo puedes quitar". La banda de la pregunta ocupaba
    # una quinta parte de la pantalla para decir una palabra. El veredicto
    # se queda -es la pregunta de la reunion- pero como una linea dentro
    # del KPI de posicion, que es donde vive esa respuesta.
    if not rn["llega"]:
        v_cls, v_txt = "crit", f'hay que tirar de póliza · cierre {eur(rn["cierre_mes"])}'
    elif rn["cierre_mes"] < col:
        v_cls, v_txt = "warn", f'llegamos justos · cierre {eur(rn["cierre_mes"])}'
    else:
        v_cls, v_txt = "ok", f'llegamos sin póliza · cierre {eur(rn["cierre_mes"])}'
    veredicto = f'<span class="chip {v_cls}">{v_txt}</span>'

    # --- los cinco numeros ----------------------------------------------
    def nk(t, v, n, estado="", det=""):
        b = (f' <button class="mas" data-m="{det}">ver</button>' if det else "")
        return (f'<div class="nk {estado}"><div class="nk-t">{esc(t)}</div>'
                f'<div class="nk-v">{v}</div>'
                f'<div class="nk-n">{n}{b}</div></div>')

    est_pos = "" if rn["saldo_hoy"] >= col else "malo"
    peor = ""
    if rn["peor_saldo"] < col:
        peor = (f' · <span class="rojo">punto flojo {esc(rn["peor_mes"])} '
                f'{eur(rn["peor_saldo"])}</span>')
    nota_pos = (f'{veredicto}<br>+ {eur(rn["polizas"])} de póliza = '
                f'{eur(rn["liquidez"])} disponibles{peor}')
    kpis = "".join([
        nk("Posición de tesorería hoy", eur(rn["saldo_hoy"]), nota_pos,
           est_pos, "m-bancos"),
        nk(f'Unlevered {esc(rn["etiqueta_mes"])} · llevamos',
           cifra(rn["unlev_mes_ej"]),
           f'levered {eur(rn["levered_mes"])} · deuda {eur(rn["deuda_mes"])}',
           "malo" if rn["unlev_mes_ej"] < 0 else "", "m-puente"),
        nk(f'Unlevered {esc(rn["etiqueta_mes"])} · proyectado',
           cifra(rn["unlev_mes_proy"]),
           f'pendiente del mes {eur(rn["unlev_mes_pdte"])}',
           "malo" if rn["unlev_mes_proy"] < 0 else ""),
        nk(f'Unlevered YTD {esc(rn["ano"])} · llevamos', cifra(rn["unlev_ytd_ej"]),
           f'{len(rn["meses_cerrados"])} meses cerrados + lo que va de mes',
           "malo" if rn["unlev_ytd_ej"] < 0 else "", "m-ytd"),
        nk(f'Unlevered YTD · proyectado', cifra(rn["unlev_ytd_proy"]),
           f'con los 3 meses siguientes {eur(rn["unlev_ytd_mas3"])}',
           "malo" if rn["unlev_ytd_proy"] < 0 else "", "m-prox"),
    ])

    # --- grafico 1: de hoy al cierre ------------------------------------
    L0 = fc["lineas"][fc["meses"][0]]
    pasos = [("Cobros", L0["cash_in"]), ("Pagos", L0["cash_out"])]

    def _flex(svg, alto):
        """El grafico llena la tarjeta en vez de dejar un hueco debajo."""
        return svg.replace(f'height="{alto}"',
                           'height="100%" preserveAspectRatio="xMidYMid meet"')

    g1 = _flex(waterfall(rn["saldo_hoy"], pasos, ancho=430, alto=300), 300)

    # --- grafico 2: el puente, que es su check --------------------------
    # EL PUENTE TIENE QUE SUMAR A LA VISTA. Antes se ensenaba el resultado
    # -variacion de bancos- y el resto se iba a un chip rojo al margen:
    # "no me cuadra el unlevered". Ahora estan las cuatro piezas, y la de
    # ajuste tiene nombre: lo que el banco ya movio y el diario aun no
    # tiene apuntado. levered = cobros + pagos + sin conciliar + sin apuntar.
    ajuste = -rn["check_resto"]
    f_p = [[f'Cobros de {esc(rn["etiqueta_mes"])} (libro diario)',
            cifra(rn["cobros_diario"])],
           [f'Pagos de {esc(rn["etiqueta_mes"])} (libro diario)',
            cifra(rn["pagos_diario"])],
           ["Sin conciliar del extracto (con signo)",
            cifra(rn["check_pendiente"])],
           ["<i>Movimientos del banco aún sin apuntar</i>",
            f'<i>{cifra(ajuste)}</i>'],
           ["<b>= LEVERED</b> · variación de bancos",
            f'<b>{cifra(rn["levered_mes"])}</b>'],
           ["Pagos de deuda (por arriba)", cifra(rn["deuda_mes"])],
           ["<b>= UNLEVERED</b>", f'<b>{cifra(rn["unlev_mes_ej"])}</b>']]
    # Un resto pequeño contra una posición de seis cifras no es un error: es
    # contabilidad yendo por detrás del banco, que es la norma. Se dice en
    # ámbar y con su nombre. El rojo se reserva para lo que no se explica.
    resto_gordo = abs(rn["check_resto"]) > max(2000.0, abs(rn["saldo_hoy"]) * 0.01)
    chk = ('<span class="chip ok">cuadra</span>' if rn["check_ok"] else
           (f'<span class="chip crit">contabilidad va {eur(abs(ajuste))} por '
            f'detrás</span>' if resto_gordo else
            f'<span class="chip warn">contabilidad va {eur(abs(ajuste))} por '
            f'detrás</span>'))
    g2 = (tabla(["El puente", "Importe"], f_p, alineacion=["", "r"],
                clases=["", "", "", "", "sub", "", "total"])
          + f'<p class="nn">Las cuatro líneas suman el levered. {chk} · '
            f'Perímetro: <b>Leaseir Technologies</b>, sin LML, Nobis, Mesia '
            f'ni USA (tu bottom-up consolida los cinco).</p>')

    # --- grafico 3: los tres meses siguientes ---------------------------
    if rn["proximos"]:
        et3 = [p["etiqueta"][:3] for p in rn["proximos"]]
        g3 = _flex(barras_agrupadas(
            et3, [("Unlevered proyectado", P["s1"],
                   [p["unlevered"] for p in rn["proximos"]]),
                  ("Saldo a cierre", P["s3"],
                   [p["saldo"] for p in rn["proximos"]])],
            ancho=430, alto=300), 300)
    else:
        g3 = '<p class="vacio">Sin horizonte proyectado.</p>'

    # --- cobros: los tres estados y el mapeo 1/2/3 ----------------------
    c = rn["cobros"]
    tot_c = (c["cobrado"] + c["vencido"] + c["sin_vencer"]) or 1
    venc_mal = c["vencido"] > rn["max_vencido"]
    barra = (f'<div class="bstack">'
             f'<i style="width:{c["cobrado"]/tot_c*100:.1f}%;background:{P["s3"]}"></i>'
             f'<i style="width:{c["vencido"]/tot_c*100:.1f}%;background:{P["crit"]}"></i>'
             f'<i style="width:{c["sin_vencer"]/tot_c*100:.1f}%;background:{P["s4"]}"></i>'
             f'</div>'
             f'<div class="bleg">'
             f'<span><i style="background:{P["s3"]}"></i>Cobrado {eur(c["cobrado"])}</span>'
             f'<span class="{"rojo" if venc_mal else ""}">'
             f'<i style="background:{P["crit"]}"></i>Vencido {eur(c["vencido"])}</span>'
             f'<span><i style="background:{P["s4"]}"></i>Sin vencer {eur(c["sin_vencer"])}</span>'
             f'</div>')
    cert = rn.get("certidumbre") or {}
    if cert:
        cols = {1: P["s3"], 2: P["s4"], 3: P["crit"]}
        barra += ('<div class="bleg map">'
                  + "".join(
                      f'<span><i style="background:{cols.get(k, P["muted"])}"></i>'
                      f'<b>{k}</b> {esc(v["nombre"].replace("Cobros ", ""))} '
                      f'{eur(v["importe"])}</span>'
                      for k, v in sorted(cert.items()))
                  + '</div>')

    # --- las ventanas de detalle ----------------------------------------
    pc = rn.get("por_cuenta") or []
    m_bancos = tabla(
        ["Cuenta", "Inicio", "Hoy", "Variación", "Contabilidad dice", "Δ"],
        [[esc(x["cuenta"]), eur(x["inicio"]), eur(x["hoy"]),
          cifra(x["variacion"]),
          "" if x.get("contable") is None else eur(x["contable"]),
          "" if x.get("dif_conta") is None else
          (f'<span class="rojo">{eur(x["dif_conta"])}</span>'
           if abs(x["dif_conta"]) > 50 else '<span class="chip ok">0</span>')]
         for x in pc]
        + [["<b>Total</b>", f'<b>{eur(sum(x["inicio"] for x in pc))}</b>',
            f'<b>{eur(sum(x["hoy"] for x in pc))}</b>',
            f'<b>{eur(sum(x["variacion"] for x in pc))}</b>', "", ""]],
        alineacion=["", "r", "r", "r", "r", "r"],
        clases=[""] * len(pc) + ["total"])
    m_puente = (tabla(["Cuenta", "Nombre", "Importe"],
                      [[f'<code>{esc(x["cuenta"])}</code>',
                        esc(x["nombre"] or "deuda"), cifra(x["importe"])]
                       for x in (rn.get("detalle_deuda") or [])] or
                      [["", "<i>sin pagos de deuda este mes</i>", ""]],
                      alineacion=["", "", "r"]))
    m_ytd = tabla(["Mes", "Levered", "Deuda", "Unlevered"],
                  [[esc(x["etiqueta"]), cifra(x["levered"]), cifra(x["deuda"]),
                    f'<b>{cifra(x["unlevered"])}</b>']
                   for x in rn["meses_cerrados"]]
                  + [[f'<b>{esc(rn["etiqueta_mes"])} (en curso)</b>',
                      cifra(rn["levered_mes"]), cifra(rn["deuda_mes"]),
                      f'<b>{cifra(rn["unlev_mes_ej"])}</b>'],
                     ["<b>YTD</b>", "", "",
                      f'<b>{cifra(rn["unlev_ytd_ej"])}</b>']],
                  alineacion=["", "r", "r", "r"],
                  clases=[""] * (len(rn["meses_cerrados"]) + 1) + ["total"])
    m_prox = tabla(["Mes", "Unlevered proyectado", "Saldo a cierre"],
                   [[esc(rn["etiqueta_mes"]) + " (en curso)",
                     cifra(rn["unlev_mes_proy"]), eur(rn["cierre_mes"])]]
                   + [[esc(p["etiqueta"]), cifra(p["unlevered"]),
                       (f'<span class="rojo">{eur(p["saldo"])}</span>'
                        if p["saldo"] < col else eur(p["saldo"]))]
                      for p in rn["proximos"]],
                   alineacion=["", "r", "r"])
    modales = "".join(
        f'<div class="modal" id="{i}"><div class="mbox">'
        f'<button class="mx" data-x="{i}">×</button>'
        f'<h3>{esc(t)}</h3>{cuerpo}</div></div>'
        for i, t, cuerpo in [
            ("m-bancos", "La posición, banco a banco", m_bancos),
            ("m-puente", "Los pagos de deuda del mes", m_puente),
            ("m-ytd", "El unlevered mes a mes", m_ytd),
            ("m-prox", "El mes en curso y los tres siguientes", m_prox)])

    return f'''
  <div class="nacho">
    <div class="nkpis">{kpis}</div>
    <div class="ngrid">
      <div class="ncard"><h3>De hoy al cierre de {esc(rn["etiqueta_mes"])}</h3>{g1}</div>
      <div class="ncard"><h3>Del levered al unlevered</h3>{g2}</div>
      <div class="ncard"><h3>Los tres meses siguientes</h3>{g3}</div>
      <div class="ncard ancho"><h3>Cobros: cobrado · vencido · sin vencer
       <span class="nn2">y el mapeo 1 / 2 / 3</span></h3>{barra}</div>
    </div>
  </div>{modales}'''


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
# JS del boton de actualizar. String normal, NO f-string: lleva llaves de
# JavaScript por todas partes y doblarlas todas seria un campo de minas.
# __API__ y __WFURL__ se sustituyen al construir la pagina.
JS_ACTUALIZAR = r"""
var API_WF = "__API__";
var API_REPO = API_WF.replace(/\/actions\/workflows\/.*$/, "");
var WF_URL = "__WFURL__";
var pollTimer = null;

function tokenGH() { try { return localStorage.getItem("lsr_gh_token") || ""; } catch (e) { return ""; } }
function cab(tok) {
  return { "Authorization": "Bearer " + tok,
           "Accept": "application/vnd.github+json",
           "X-GitHub-Api-Version": "2022-11-28" };
}
function estado(txt, spin) {
  var e = document.getElementById("refEstado");
  if (e) e.innerHTML = (spin ? '<span class="spin"></span>' : '') + txt;
}
function abrirConf() { var c = document.getElementById("refConf"); if (c) c.hidden = false; }
function cerrarConf() { var c = document.getElementById("refConf"); if (c) c.hidden = true; }
function guardarToken() {
  var v = (document.getElementById("refTok").value || "").trim();
  if (!v) return;
  try { localStorage.setItem("lsr_gh_token", v); } catch (e) {}
  document.getElementById("refTok").value = "";
  cerrarConf();
  forzar();
}
function borrarToken() {
  try { localStorage.removeItem("lsr_gh_token"); } catch (e) {}
  estado("llave quitada de este navegador", false);
}
function errorLlave(codigo) {
  estado("la llave no vale (HTTP " + codigo + "): caducada o sin permiso de Actions sobre el repo. " +
         '<a href="#" onclick="abrirConf();return false">cambiar llave</a> · ' +
         '<a href="' + WF_URL + '" target="_blank" rel="noopener">lanzar desde GitHub</a>', false);
  var b = document.getElementById("btnRef"); if (b) b.disabled = false;
}
function forzar() {
  var tok = tokenGH();
  if (!tok) { abrirConf(); return; }
  var b = document.getElementById("btnRef"); if (b) b.disabled = true;
  estado("lanzando la actualización…", true);
  fetch(API_WF + "/dispatches", {
    method: "POST", headers: cab(tok),
    body: JSON.stringify({ ref: "main" })
  }).then(function (r) {
    if (r.status === 204) { setTimeout(function () { buscarRun(tok, 0); }, 5000); }
    else if (r.status === 401 || r.status === 403 || r.status === 404) { errorLlave(r.status); }
    else { estado("GitHub ha contestado HTTP " + r.status + "; reintenta en un momento", false); if (b) b.disabled = false; }
  }).catch(function () {
    estado("sin conexión con la API de GitHub; reintenta", false); if (b) b.disabled = false;
  });
}
function buscarRun(tok, intento) {
  fetch(API_WF + "/runs?per_page=1&event=workflow_dispatch", { headers: cab(tok) })
    .then(function (r) { return r.json(); })
    .then(function (d) {
      var run = d.workflow_runs && d.workflow_runs[0];
      var reciente = run && (Date.now() - new Date(run.created_at).getTime()) < 120000;
      if (run && reciente) {
        try { localStorage.setItem("lsr_run", JSON.stringify({ id: run.id, t0: Date.now() })); } catch (e) {}
        medirDuracion(tok);
        poll(run.id, Date.now());
      } else if (intento < 4) {
        setTimeout(function () { buscarRun(tok, intento + 1); }, 4000);
      } else {
        estado('lanzado, pero no encuentro el run; míralo <a href="' + WF_URL +
               '" target="_blank" rel="noopener">en GitHub</a>', false);
        var b = document.getElementById("btnRef"); if (b) b.disabled = false;
      }
    });
}
function minutos(t0) {
  var s = Math.floor((Date.now() - t0) / 1000);
  return Math.floor(s / 60) + "m " + ("0" + (s % 60)).slice(-2) + "s";
}
// Cuanto suele tardar: la MEDIA REAL de los ultimos runs buenos, pedida a la
// API una vez por actualizacion. Un porcentaje contra un numero inventado es
// teatro; contra la media de los ultimos cinco, es una estimacion honesta.
var durTipica = 510;   // arranque: 8m30s, hasta que llega la media real
function medirDuracion(tok) {
  fetch(API_WF + "/runs?per_page=6&status=success", { headers: cab(tok) })
    .then(function (r) { return r.json(); })
    .then(function (d) {
      var runs = (d.workflow_runs || []).slice(0, 5);
      var ds = runs.map(function (x) {
        return (new Date(x.updated_at) - new Date(x.run_started_at)) / 1000;
      }).filter(function (x) { return x > 60 && x < 3600; });
      if (ds.length >= 2) durTipica = ds.reduce(function (a, b) { return a + b; }, 0) / ds.length;
    }).catch(function () {});
}
function pct(t0) {
  var p = Math.min(97, Math.round(100 * (Date.now() - t0) / 1000 / durTipica));
  return p + "%";
}
function poll(id, t0) {
  var tok = tokenGH(); if (!tok) return;
  if (pollTimer) clearTimeout(pollTimer);
  fetch(API_REPO + "/actions/runs/" + id, { headers: cab(tok) })
    .then(function (r) {
      if (r.status === 401 || r.status === 403) { errorLlave(r.status); return null; }
      return r.json();
    })
    .then(function (d) {
      if (!d) return;
      if (d.status === "completed") {
        try { localStorage.removeItem("lsr_run"); } catch (e) {}
        if (d.conclusion === "success") {
          estado("hecho: publicando la página… (≈1 min)", true);
          setTimeout(function () {
            location.replace(location.pathname + "?v=" + Date.now());
          }, 75000);
        } else {
          estado('la actualización ha fallado (' + (d.conclusion || "?") + '): ' +
                 '<a href="' + d.html_url + '" target="_blank" rel="noopener">ver el porqué</a>', false);
          var b = document.getElementById("btnRef"); if (b) b.disabled = false;
        }
      } else {
        var fase = d.status === "queued" ? "en cola en GitHub" : "leyendo Holded y recalculando";
        estado(fase + "… <b>" + pct(t0) + "</b> · " + minutos(t0) +
               " <span class=\"apagado\">de ~" + Math.round(durTipica / 60) + " min</span>", true);
        pollTimer = setTimeout(function () { poll(id, t0); }, 12000);
      }
    })
    .catch(function () { pollTimer = setTimeout(function () { poll(id, t0); }, 20000); });
}
(function () {
  var g;
  try { g = JSON.parse(localStorage.getItem("lsr_run") || "null"); } catch (e) { g = null; }
  if (g && Date.now() - g.t0 < 20 * 60000) {
    var b = document.getElementById("btnRef"); if (b) b.disabled = true;
    var tk = tokenGH(); if (tk) medirDuracion(tk);
    poll(g.id, g.t0);
  } else if (g) {
    try { localStorage.removeItem("lsr_run"); } catch (e) {}
  }
})();
"""


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
    eje.setdefault("saldo_hoy", (eje.get("banco") or {}).get("saldo_hoy",
                                                             fc["saldo_actual"]))

    est_fcf = "ok" if eje.get("fcf", 0) >= 0 else "mal"
    est_fin = "ok" if saldo_cierre > 200_000 else ("aviso" if saldo_cierre > 0 else "mal")

    # Nota de pólizas. Holded no publica el limite, asi que sin limite escrito
    # en config no se puede decir el disponible. Decir "+ 0 €" seria mentir por
    # omision: se lee como que no hay financiacion, y no es lo mismo que no
    # saberlo.
    sin_lim = fc.get("polizas_sin_limite") or []
    if fc.get("polizas_limite"):
        nota_pol = (f"pólizas: {eur(fc['polizas_disponible'])} libres · "
                    f"dispuesto {eur(fc.get('polizas_dispuesto') or 0)} de "
                    f"{eur(fc['polizas_limite'])}")
    elif sin_lim:
        nota_pol = f"pólizas: {esc(', '.join(sin_lim))}, límite sin configurar"
    else:
        nota_pol = "sin pólizas"

    # si el saldo contable y el listado de tesoreria no dicen lo mismo, se
    # avisa: una cuenta que figura a cero en el listado y tiene dinero dentro
    # es exactamente lo que paso con la segunda cuenta de Caixa
    # Cuántas cuentas del listado no tienen saldo pero sí cuenta contable con
    # movimiento: es la forma de que la cuenta de Caixa que falta se anuncie
    # sola en vez de descubrirse restando totales.

    # la posicion es contable (libro diario); lo que Holded declara a mano se
    # dice al lado, con su diferencia, para que nadie confunda las dos fotos
    sc_ = fc.get("saldo_contable")
    if sc_ is not None and abs(sc_ - fc["saldo_actual"]) > 1:
        nota_pol = (f"tesorería (extracto) · contabilidad dice {eur(sc_)}, "
                    f"{eur(fc['saldo_actual'] - sc_)} por apuntar · " + nota_pol)
    else:
        nota_pol = "tesorería (extracto) · " + nota_pol
    kpis = "".join([
        kpi("Posición bancaria hoy", eur(fc["saldo_actual"]), nota_pol),
        kpi(f"Unlevered FCF {m0['etiqueta']} · lo que llevamos",
            eur(eje.get("fcf", 0)),
            # los tres numeros tienen que sumar al titular a la vista, o el
            # lector deja de fiarse de todo lo demas
            (f"Levered {eur(eje.get('levered', 0))} más pagos de deuda "
             f"{eur(-eje.get('deuda', 0))}"
             if eje.get("fuente") == "saldo del banco" else
             f"Caja {eur(eje.get('variacion_caja', 0))} menos financiación "
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

    filas_fc, clases, claves_fc = [], [], []
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
        claves_fc.append(k)

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
    elif cuadre.get("fuente") == "apertura contra saldo de hoy":
        # El check completo: contabilidad + pendiente de conciliar = banco.
        # La diferencia bruta NO es el veredicto; el veredicto es lo que queda
        # despues de sumar el pendiente, que es descuadre de verdad.
        ok = cuadre.get("cuadra_conciliado", cuadre["cuadra"])
        pn = cuadre.get("pendiente_neto", 0.0)
        resto = cuadre.get("resto_conciliar", cuadre["diferencia"])
        f_ck = [
            [f'Saldo de apertura de bancos ({esc(cuadre["origen_apertura"])})',
             eur(cuadre["saldo_apertura"])],
            ["Cobros del mes (libro diario)", eur(cuadre["cobros_ejecutados"])],
            ["Pagos del mes (libro diario)",
             f'<span class="neg">{eur(cuadre["pagos_ejecutados"])}</span>'],
            ["<b>Apertura + flujos del diario</b>",
             f'<b>{eur(cuadre["saldo_teorico"])}</b>'],
            ["Saldo de hoy (contabilidad + extracto sin conciliar)",
             eur(cuadre["saldo_hoy"])],
            ["Diferencia contabilidad − banco", eur(cuadre["diferencia"])],
            ["Pendiente de conciliar en el extracto (con signo)", eur(pn)],
            ["<b>Resto sin explicar</b>",
             f'<b><span class="{"" if ok else "neg"}">{eur(resto)}</span></b>'],
        ]
        cuadre_html = (
            f'<div class="nota-cuadre {"ok" if ok else "mal"}">'
            f'<b>{"CUADRA" if ok else "NO CUADRA"}</b> — contabilidad más lo '
            f'pendiente de conciliar {"explica" if ok else "NO explica"} el '
            f'saldo del banco. Tolerancia {eur(cuadre["tolerancia"])}.'
            f'</div>'
            + tabla(["Concepto", cuadre["etiqueta"]], f_ck,
                    alineacion=["", "r"],
                    clases=["", "", "", "sub", "", "", "", "total"]))
        pc = cuadre.get("pdte_conciliar") or []
        if pc:
            cuadre_html += (
                '<h2 style="font-size:15px;margin-top:22px">Lo que Holded tiene '
                'sin conciliar</h2>'
                '<p class="h2n">Movimientos que están en el extracto del banco y '
                'todavía no apuntados en contabilidad. Es la diferencia entre lo '
                'que dice el banco y lo que dice el mayor, y lo que hay que '
                'conciliar para cerrarla. El importe es la suma en valor '
                'absoluto: un cobro y un pago del mismo tamaño suman aquí y se '
                'anulan en el saldo.</p>'
                + tabla(["Cuenta", "Movimientos", "Importe"],
                        [[esc(x["cuenta"]), f'{x["movimientos"]}', eur(x["importe"])]
                         for x in pc], alineacion=["", "r", "r"]))
        nat = cuadre.get("naturaleza") or []
        if nat:
            cuadre_html += (
                '<details><summary>De qué se componen esos cobros y pagos</summary>'
                + tabla(["Contrapartida", "Importe", "Apuntes"],
                        [[esc(x["concepto"]),
                          f'<span class="{"neg" if x["importe"] < 0 else ""}">'
                          f'{eur(x["importe"])}</span>', f'{x["apuntes"]}']
                         for x in nat], alineacion=["", "r", "r"])
                + '</details>')
    elif cuadre.get("fuente") == "libro diario":
        # Del diario no sale residuo: cada movimiento lleva su contrapartida en
        # el mismo asiento. En vez de un "no cuadra por X" se enseña de que se
        # compone el flujo del mes, euro a euro.
        nat = cuadre.get("naturaleza") or []
        f_na = [[esc(x["concepto"]),
                 f'<span class="{"neg" if x["importe"] < 0 else ""}">'
                 f'{eur(x["importe"])}</span>', f'{x["apuntes"]}'] for x in nat]
        f_na.append(["<b>Variación de caja del mes</b>",
                     f'<b>{eur(cuadre["variacion_bancaria"])}</b>', ""])
        cuadre_html = (
            '<div class="nota-cuadre ok"><b>CUADRA POR CONSTRUCCIÓN</b> — sale del '
            'libro diario, donde cada movimiento de caja lleva su contrapartida '
            'en el mismo asiento. Todo el flujo del mes queda explicado por '
            'naturaleza y no hay residuo posible. Antes se emparejaban importes '
            'del extracto con liquidaciones de facturas y quedaban 178 000 € sin '
            'explicar, que eran justamente los pagos sin factura.</div>'
            + tabla(["Contrapartida", cuadre["etiqueta"], "Apuntes"], f_na,
                    alineacion=["", "r", "r"],
                    clases=[""] * (len(f_na) - 1) + ["total"]))
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
        # Las tarjetas no le importan a nadie mirando la posicion: van a un
        # desplegable al pie, no mezcladas con las cuentas.
        vis_t = vis[vis["tipo"] == "tarjeta"]
        vis = vis[vis["tipo"] != "tarjeta"]
        f_b = [[esc(r["cuenta"]), NOM_TIPO.get(r["tipo"], "Cuenta"), eur(r["saldo"])]
               for _, r in vis.iterrows()]
        t_ban = tabla(["Cuenta", "Tipo", "Saldo"], f_b) if f_b else \
            '<p class="vacio">Todas las cuentas a cero.</p>'
        if not vis_t.empty:
            t_ban += (
                f'<details><summary>Tarjetas — {eur(float(vis_t["saldo"].sum()))}, '
                f'se cargan el mes siguiente</summary>'
                + tabla(["Tarjeta", "Saldo"],
                        [[esc(r["cuenta"]), eur(r["saldo"])]
                         for _, r in vis_t.iterrows()], alineacion=["", "r"])
                + '</details>')
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

    # De donde sale exactamente la posicion, cuenta contable a cuenta contable.
    # La lista de tesoreria de Holded daba una de las dos cuentas de Caixa a
    # cero y la posicion salia 23.806 corta. Con el desglose delante, decir
    # que linea sobra o falta es mirar, no deducir.
    conc = fc.get("conciliacion_caja") or []
    if conc:
        f_c, cl_c = [], []
        for c in sorted(conc, key=lambda x: (not x.get("banco"),
                                             -(abs(x.get("recons") or 0)))):
            marca, clase = "", ""
            if not c.get("banco"):
                marca = ' <span class="chip">no es banco, fuera</span>'
            elif c.get("rescatada"):
                marca = (f' <span class="chip crit">saldo tuyo, '
                         f'{esc(c["manual"])}</span>' if c.get("manual")
                         else ' <span class="chip crit">reconstruida</span>')
                clase = "res"
            f_c.append([esc(c["num"]) or "—", esc(c["cuenta"]) + marca,
                        "—" if c.get("listado") is None else eur(c["listado"]),
                        "—" if c.get("recons") is None else eur(c["recons"]),
                        eur(c.get("pte") or 0),
                        "—" if c.get("estimado") is None else eur(c["estimado"]),
                        "—" if c.get("dif") is None else eur(c["dif"])])
            cl_c.append(clase)
        tot_l = sum(c["listado"] for c in conc if c.get("listado") is not None)
        f_c.append(["<b>Total</b>", "<b>posición publicada</b>",
                    f"<b>{eur(tot_l + (fc.get('rescatado') or 0))}</b>",
                    "", "", "", ""])
        cl_c.append("")
        n_ok, n_tot = (fc.get("recons_n") or (0, 0))
        veredicto = (
            f'Cuadra en {n_ok} de las {n_tot} cuentas que Holded sí sincroniza, '
            f'suficiente para dar el método por bueno en la que no.'
            if fc.get("recons_ok") and n_tot else
            f'Solo cuadra en {n_ok} de {n_tot} cuentas conocidas, así que no se '
            f'aplica: la posición se queda con el listado tal cual.')
        t_ban += (
            '<details><summary>Contraste con contabilidad — de dónde sale la '
            'posición</summary>'
            '<p class="h2n">Cada cuenta de tesorería frente a su cuenta '
            'contable, enlazadas por el número de cuenta que da el propio '
            'Holded, no por el nombre. <b>Listado</b> es el saldo que declara '
            'Holded. <b>Contabilidad</b> es el saldo del 1 de enero (del '
            'asiento de apertura) más lo movido desde entonces. Las dos cifras '
            'no tienen por qué coincidir, y no deben: se diferencian en lo que '
            'está en el extracto y todavía no apuntado, que es la columna '
            '<b>Pendiente</b>. La prueba es que <b>contabilidad + pendiente = '
            'banco</b>; la última columna es lo que sobra o falta para que '
            'cuadre. ' + esc(veredicto) + '</p>'
            + tabla(["Cuenta contable", "Cuenta", "Listado", "Contabilidad",
                     "Pendiente", "Contab. + pdte.", "Dif."], f_c,
                    alineacion=["", "", "r", "r", "r", "r", "r"], clases=cl_c)
            + '</details>')

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

    # ---- que se cobra y que no ------------------------------------------
    # Un forecast que da por cobrado todo lo vencido no es un forecast. Aqui
    # se parte en dos, con nombre e importe, para que el proyectado se pueda
    # mirar a la cara.
    t_cobrab = ""
    cbb = meta.get("cobrabilidad")
    if cbb is not None:
        dfc, tot = cbb
        if dfc is not None and not dfc.empty:
            # EDITABLE. Cada factura lleva su casilla de "se cobra" y su
            # importe. Al tocar cualquiera, la proyeccion editada se recalcula
            # en el momento, y el boton genera el bloque `previsiones` listo
            # para pegar en config.yaml, que es donde la decision se hace
            # permanente: una pagina estatica no puede guardar nada sola, y
            # fingir que guarda seria mentir.
            _seq = [0]

            def por_cliente(sub):
                if sub.empty:
                    return '<p class="vacio">Ninguna.</p>'
                g = []
                for cl, gg in sorted(sub.groupby("cliente"),
                                     key=lambda kv: -kv[1]["pendiente_cobro"].sum()):
                    filas = []
                    for _, r in gg.sort_values("pendiente_cobro",
                                               ascending=False).iterrows():
                        _seq[0] += 1
                        k = _seq[0]
                        entra = bool(r["entra"])
                        defecto = r["pendiente_cobro"] if entra else 0.0
                        chk = (f'<input type="checkbox" class="cbx" data-k="{k}" '
                               f'data-num="{esc(str(r["num"]))}" '
                               f'data-def="{defecto:.0f}" '
                               f'{"checked" if entra else ""} '
                               f'onchange="recalcCob()">')
                        inp = (f'<input type="number" class="cbi" data-k="{k}" '
                               f'value="{r["pendiente_cobro"]:.0f}" step="100" '
                               f'oninput="recalcCob()">')
                        filas.append([esc(str(r["num"])),
                                      esc(str(r.get("vencimiento") or "")),
                                      esc(str(r.get("motivo") or "")),
                                      eur(r["pendiente_cobro"]), chk, inp])
                    g.append((cl, f'<b>{eur(gg["pendiente_cobro"].sum())}</b>', filas))
                return detalle_desplegable(
                    g, ["Factura", "Vencimiento", "Motivo", "Pendiente",
                        "¿Se cobra?", "Importe real"],
                    alineacion=["", "", "", "r", "c", "r"])

            n_e = int(dfc["entra"].sum())
            t_cobrab = f'''
  <section>
    <h2>Qué vamos a cobrar y qué no — edítalo tú</h2>
    <p class="h2n">El corte automático es el retraso: lo vencido hace más de
     {tot["dias"]} días no se da por cobrado (<code>cobros.dias_dudoso</code>).
     Pero la última palabra es tuya: marca qué se cobra y por cuánto, la
     proyección se recalcula al momento, y el botón te genera el bloque
     <code>previsiones</code> para pegar en <code>config.yaml</code> y que la
     decisión quede fija en las siguientes actualizaciones.</p>
    <div class="kpis">
      {kpi("Se da por cobrable", eur(tot["entra"]), f"{n_e} facturas", "ok")}
      {kpi("No se cuenta", eur(tot["fuera"]),
           f'{tot["n_fuera"]} facturas vencidas hace más de {tot["dias"]} días', "mal")}
    </div>
    <div class="edit-bar">Tu proyección editada de cobros:
      <b id="cobEd">{eur(tot["entra"])}</b>
      <span class="apagado">(el motor da por cobrable {eur(tot["entra"])})</span>
      <button class="btn-mini" onclick="yamlCob()">Generar previsiones para config.yaml</button>
    </div>
    <pre id="cobYaml" hidden></pre>
    <h2 style="font-size:15px;margin-top:20px">Lo que no se cuenta</h2>
    {por_cliente(dfc[~dfc["entra"]])}
    <h2 style="font-size:15px;margin-top:22px">Lo que sí se espera cobrar</h2>
    {por_cliente(dfc[dfc["entra"]])}
  </section>'''

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

    # El desglose ya no es una seccion aparte con sus parrafos: cuelga de la
    # propia linea del cuadro. Alejandro lo dijo claro: los totales se ven
    # siempre y el detalle se despliega si se quiere. Una seccion que repite
    # los mismos numeros mas abajo, con una explicacion encima de cada bloque,
    # es paja entre el dato y quien lo lee.
    def _desglose(titulo, filas, nota=""):
        if not filas:
            return ""
        cuerpo = [_fila_meses(n, v) for n, v in filas]
        return tabla(["Detalle"] + etiquetas, cuerpo,
                     alineacion=[""] + ["r"] * len(meses))

    des = []
    detalles = {}

    if not cli.empty:
        top = cli.reindex(cli[[f"teorico_{m}" for m in meses]].abs().sum(axis=1)
                          .sort_values(ascending=False).index).head(25)
        # COMPOSICION HASTA LA FACTURA. El total del cliente y, debajo, cada
        # factura con su parte en cada mes. Alejandro: "el forecast lo quiero
        # tambien con composicion de facturas". Sin esto, el numero del
        # cliente hay que creerselo.
        dcx = fc.get("detalle_cobros")
        filas_cc = []
        for _, r in top.iterrows():
            filas_cc.append((r["cliente"],
                             [float(r[f"teorico_{m}"]) for m in meses]))
            if dcx is not None and not dcx.empty:
                fs = dcx[dcx["cliente"] == r["cliente"]]
                for _, f in fs.iterrows():
                    vals = [float(f[f"teorico_{m}"]) for m in meses]
                    if sum(abs(v) for v in vals) < 0.01:
                        continue
                    vto = f.get("vencimiento")
                    filas_cc.append((f"· {f['num']}"
                                     + (f" (vto {vto})" if vto else ""), vals))
        detalles["cobro_clientes"] = _desglose("", filas_cc)

    rent = fc.get("rentings")
    if rent is not None and not rent.empty:
        for tipo, clave in [("renting", "rentings_sin_factura"),
                            ("fusion", "ventas_fusion_lml")]:
            g = rent[rent["tipo"] == tipo] if "tipo" in rent.columns else rent
            if g.empty:
                continue
            porcli = {}
            for _, r in g.iterrows():
                porcli.setdefault(r["cliente"], [0.0] * len(meses))
                if r["mes"] in meses:
                    porcli[r["cliente"]][meses.index(r["mes"])] += float(r["importe"])
            detalles[clave] = _desglose(
                "", sorted(porcli.items(), key=lambda x: -sum(x[1])))

    sf = (fc.get("detalle") or {}).get("sin_facturar") or []
    if sf:
        detalles["ventas_sin_facturar"] = _desglose(
            "", [(f'{x["concepto"]} · {x["unidades"]} x {eur(x["precio"])} '
                  f'+ {x["iva"]:.0%} IVA',
                  [x["unidades"] * x["precio"] * (1 + x["iva"])]
                  + [0.0] * (len(meses) - 1)) for x in sf])

    aj = (fc.get("detalle") or {}).get("ajustes") or []
    if aj:
        detalles["ajustes_cobros"] = _desglose(
            "", [(x["concepto"], [float(x["importe"])] + [0.0] * (len(meses) - 1))
                 for x in aj])

    if not prov.empty:
        topp = prov.reindex(prov[[f"pago_{m}" for m in meses]].abs().sum(axis=1)
                            .sort_values(ascending=False).index).head(25)
        # Facturas del proveedor: cada una cae en el mes de su vencimiento
        # (los vencidos, arrastrados al mes en curso, que es el criterio del
        # forecast). El total del proveedor deja de ser un acto de fe.
        dpx = fc.get("detalle_pagos")
        fin_mes = {m: (m[:4] + m[4:]) for m in meses}
        filas_pp = []
        for _, r in topp.iterrows():
            filas_pp.append((r["proveedor"],
                             [-abs(float(r[f"pago_{m}"])) for m in meses]))
            if dpx is not None and not dpx.empty:
                fs = dpx[(dpx["proveedor"] == r["proveedor"])
                         & (dpx["pendiente"] > 0.01)]
                for _, f in fs.iterrows():
                    v = f.get("vencimiento")
                    mv = f"{v.year}{v.month:02d}" if hasattr(v, "year") else ""
                    idx = 0 if (not mv or mv <= meses[0]) else \
                        (meses.index(mv) if mv in meses else None)
                    if idx is None:
                        continue
                    vals = [0.0] * len(meses)
                    vals[idx] = -float(f["pendiente"])
                    filas_pp.append((f"· {f['num']}"
                                     + (f" (vto {v})" if v else ""), vals))
        detalles["pago_proveedores"] = _desglose("", filas_pp)

    recu = fc.get("recurrentes")
    if recu is not None and not recu.empty:
        col = "etiqueta" if "etiqueta" in recu.columns else recu.columns[0]
        porprov = {}
        for _, r in recu.iterrows():
            porprov.setdefault(r[col], [0.0] * len(meses))
            if r["mes"] in meses:
                porprov[r[col]][meses.index(r["mes"])] += float(r["proyectado"])
        detalles["recurrentes_proyectados"] = _desglose(
            "", sorted(porprov.items(), key=lambda x: sum(x[1])))

    det = fc.get("detalle") or {}
    pag_fij = (det.get("fijos_pagados") or {})
    for clave in ("salarios", "cuotas_sl", "otros_fijos"):
        d0 = det.get(clave) or []
        if not d0:
            continue
        filas = [(x["concepto"], [float(x["importe"])] * len(meses)) for x in d0]
        hecho = float(pag_fij.get(clave, 0) or 0)
        if hecho:
            filas.append((f"Ya pagado en {m0['etiqueta']}",
                          [hecho] + [0.0] * (len(meses) - 1)))
        detalles[clave] = _desglose("", filas)

    # El cuadro se monta a mano en vez de con tabla() porque cada linea que
    # tiene desglose lleva colgada una fila oculta con su detalle. Asi los
    # totales se ven siempre y el detalle se abre solo si se pide, en el mismo
    # sitio donde esta el numero y no en otra seccion mas abajo.
    cab = "".join(f'<th class="{"" if i == 0 else "r"}">{esc(h)}</th>'
                  for i, h in enumerate(["Concepto"] + etiquetas))
    cuerpo = []
    for i, (f, cl, k) in enumerate(zip(filas_fc, clases, claves_fc)):
        det_html = detalles.get(k)
        marca = ('<span class="abre">▸</span>' if det_html else
                 '<span class="abre vacia"></span>')
        celdas = (f'<td>{marca}{f[0]}</td>'
                  + "".join(f'<td class="r">{x}</td>' for x in f[1:]))
        cls = " ".join(x for x in (cl, "desplegable" if det_html else "") if x)
        attr = f' class="{cls}"' if cls else ""
        if det_html:
            attr += f' data-det="fcd{i}"'

        cuerpo.append(f"<tr{attr}>{celdas}</tr>")
        if det_html:
            cuerpo.append(
                f'<tr class="fc-det" id="fcd{i}" hidden>'
                f'<td colspan="{len(etiquetas) + 1}">{det_html}</td></tr>')
    tabla_fc = (f'<table class="fc"><thead><tr>{cab}</tr></thead>'
                f'<tbody>{"".join(cuerpo)}</tbody></table>')

    # ---- previsiones manuales ---------------------------------------------
    # Una cifra corregida a mano que no se sabe corregida es peor que la
    # original: se enseña que decia el motor, que dice la prevision y cuanto
    # cambia. Y si una clave no casa con nadie, se dice en rojo.
    pv = fc.get("previsiones") or []
    if pv:
        f_pv = []
        for x in pv:
            if x.get("aplicada"):
                f_pv.append([
                    f'{esc(x["clave"])} <span class="chip ok">'
                    f'{esc(x["tipo"])}</span>',
                    esc(nombre_mes(x["mes"]) if len(x["mes"]) == 6 else x["mes"]),
                    eur(x["antes"]), eur(x["despues"]),
                    f'<span class="{"neg" if x["diferencia"] < 0 else ""}">'
                    f'{eur(x["diferencia"])}</span>',
                    esc(x["nota"])])
            else:
                f_pv.append([
                    f'{esc(x["clave"])} <span class="chip crit">sin aplicar</span>',
                    esc(x["mes"]), "—", "—",
                    f'<span class="neg">{esc(x["motivo"])}</span>', esc(x["nota"])])
        aplic = [x for x in pv if x.get("aplicada")]
        if aplic:
            f_pv.append(["<b>Efecto total sobre el forecast</b>", "", "", "",
                         f'<b>{eur(sum(x["diferencia"] for x in aplic))}</b>', ""])
        t_prev = tabla(["Cliente / proveedor", "Mes", "Decía el motor",
                        "Dice la previsión", "Diferencia", "Por qué"], f_pv,
                       alineacion=["", "", "r", "r", "r", ""],
                       clases=[""] * (len(f_pv) - (1 if aplic else 0))
                              + (["total"] if aplic else []))
    else:
        t_prev = ('<p class="vacio">Sin previsiones manuales: el forecast va tal '
                  'cual sale de Holded y del calendario de Eli. Para corregir lo '
                  'que sabes que no se va a cobrar o pagar, edita la sección '
                  '<code>previsiones</code> de <code>config.yaml</code>.</p>')

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
    if eje.get("fuente") == "saldo del banco":
        bk = eje.get("banco") or {}
        f_pu = [
            [f'Saldo del banco al empezar {esc(m0["etiqueta"])}',
             eur(bk.get("saldo_inicio", 0))],
            ["Saldo del banco hoy", eur(bk.get("saldo_hoy", 0))],
            ["<b>Variación del saldo bancario</b>",
             f'<b><span class="{"neg" if bk.get("variacion_bancos", 0) < 0 else ""}">'
             f'{eur(bk.get("variacion_bancos", 0))}</span></b>'],
        ]
        # De donde sale esa variacion: cobros y pagos del libro diario mas lo
        # pendiente de conciliar, CON SIGNO. Son numeros, y tienen que cerrar:
        # contabilidad + pendiente = banco. Si queda resto, se dice en rojo.
        if cuadre and cuadre.get("pendiente_neto") is not None:
            c_dia = cuadre.get("cobros_ejecutados", 0)
            p_dia = cuadre.get("pagos_ejecutados", 0)
            pn = cuadre.get("pendiente_neto", 0)
            resto_pu = bk.get("variacion_bancos", 0) - (c_dia + p_dia) - pn
            f_pu += [
                [f'&nbsp;&nbsp;Cobros de {esc(m0["etiqueta"])} (libro diario)',
                 eur(c_dia)],
                [f'&nbsp;&nbsp;Pagos de {esc(m0["etiqueta"])} (libro diario)',
                 f'<span class="neg">{eur(p_dia)}</span>'],
                ['&nbsp;&nbsp;Pendiente de conciliar en el extracto (con signo)',
                 eur(pn)],
            ]
            if abs(resto_pu) > cuadre.get("tolerancia", 1):
                f_pu.append([
                    '&nbsp;&nbsp;<span class="rojo">Resto sin explicar: '
                    'movimientos que faltan en el diario o en el extracto</span>',
                    f'<span class="rojo">{eur(resto_pu)}</span>'])
        f_pu.append(["<b>LEVERED FCF</b> = variación del saldo bancario",
                     f'<b>{eur(bk.get("levered", 0))}</b>'])
        for x in eje.get("detalle_deuda") or []:
            f_pu.append([f"&nbsp;&nbsp;<code>{esc(x['cuenta'])}</code> "
                         f"{esc(x['nombre'] or 'deuda')}",
                         f'<span class="{"neg" if x["importe"] < 0 else ""}">'
                         f'{eur(x["importe"])}</span>'])
        gt = bk.get("gasto_tarjetas", 0)
        if abs(gt) > 0.5:
            f_pu.append([
                "<i>Tarjetas, que no son deuda: gasto que vuelca al mes "
                "siguiente. Se quedan dentro del unlevered</i>",
                f'<i>{eur(gt)}</i>'])
        f_pu += [
            ["Pagos de deuda del mes (principal, intereses y comisiones)",
             f'<span class="{"neg" if bk.get("deuda", 0) < 0 else ""}">'
             f'{eur(bk.get("deuda", 0))}</span>'],
            ["<b>UNLEVERED FCF</b> = levered − pagos de deuda",
             f'<b>{eur(bk.get("unlevered", 0))}</b>'],
        ]
        n_det = len(eje.get("detalle_deuda") or []) + (
            1 if abs(bk.get("gasto_tarjetas", 0)) > 0.5 else 0)
        n_cab = len(f_pu) - 3 - n_det  # todo lo anterior al LEVERED
        cl_pu = [""] * n_cab + ["sub"] + [""] * n_det + ["sub", "total"]
        gm = bk.get("gasto_tarjeta_mes", 0)
        nota_tarj = ("" if abs(gm) < 0.5 else
                     f'<p class="h2n">Aparte, y sin tocar el levered: '
                     f'{eur(gm)} de gasto en tarjeta de {esc(m0["etiqueta"])} '
                     f'que el banco no carga hasta el mes que viene.</p>')

        # SU CHECK, BANCO A BANCO, DELANTE. La apertura es la del extracto
        # escrita a mano; el descuadre de cada banco es (apertura +
        # movimientos - saldo hoy): donde no sea cero, ahi le faltan
        # movimientos a Holded. Es la fila K120 de su maestra hecha tabla.
        pc = bk.get("por_cuenta") or []
        t_bancos = ""
        if pc:
            con_desc = any(x.get("descuadre") is not None for x in pc)
            # contabilidad al lado, nunca dentro: la Δ contra el saldo del
            # banco es lo que falta por apuntar o conciliar en esa cuenta
            con_ct = any(x.get("contable") is not None for x in pc)
            f_pc, cl_pc = [], []
            for x in pc:
                d = x.get("descuadre")
                chip = ""
                if d is not None and abs(d) > 50:
                    chip = f'<span class="rojo">{eur(d)}</span>'
                elif d is not None:
                    chip = '<span class="chip ok">0</span>'
                dc = x.get("dif_conta")
                col_c = ("" if x.get("contable") is None else eur(x["contable"]))
                col_dc = ("" if dc is None else
                          (f'<span class="rojo">{eur(dc)}</span>'
                           if abs(dc) > 50 else '<span class="chip ok">0</span>'))
                fte = x.get("fuente") or ""
                marca = ("" if fte.startswith("tesorería") and "sin" not in fte
                         else f' <span class="apagado">({esc(fte)})</span>')
                fila = [esc(x["cuenta"]) + marca,
                        eur(x["inicio"]), eur(x["hoy"]),
                        f'<span class="{"neg" if x["variacion"] < 0 else ""}">'
                        f'{eur(x["variacion"])}</span>', f'{x["n"]}']
                if con_ct:
                    fila += [col_c, col_dc]
                if con_desc:
                    fila.append(chip)
                f_pc.append(fila)
                cl_pc.append("")
            tot = ["<b>Total</b>",
                   f'<b>{eur(sum(x["inicio"] for x in pc))}</b>',
                   f'<b>{eur(sum(x["hoy"] for x in pc))}</b>',
                   f'<b>{eur(sum(x["variacion"] for x in pc))}</b>', ""]
            if con_ct:
                tot += [f'<b>{eur(sum(x["contable"] for x in pc if x.get("contable") is not None))}</b>',
                        f'<b>{eur(sum(x["dif_conta"] for x in pc if x.get("dif_conta") is not None))}</b>']
            if con_desc:
                tot.append(f'<b>{eur(sum(x["descuadre"] for x in pc if x.get("descuadre") is not None))}</b>')
            f_pc.append(tot)
            cl_pc.append("total")
            cabs = ["Cuenta", "Inicio", "Hoy", "Variación", "Movs."]
            if con_ct:
                cabs += ["Contabilidad dice", "Δ"]
            if con_desc:
                cabs.append("Descuadre")
            t_bancos = tabla(cabs, f_pc,
                             alineacion=[""] + ["r"] * (len(cabs) - 1),
                             clases=cl_pc)
        t_puente = (t_bancos + nota_tarj
                    + '<h2 style="font-size:15px;margin-top:22px">Y de la '
                      'variación al unlevered</h2>'
                    + tabla(["Concepto", "Importe"], f_pu,
                            alineacion=["", "r"], clases=cl_pu))
        # El hueco declarado por Holded entre banco y contabilidad. Cuando el
        # unlevered no cuadra contra el bottom-up, esto es lo primero que hay
        # que mirar, y hasta ahora no se veia en ningun sitio.
        # Lo sin conciliar, CLASIFICADO. No todo lo que Holded declara sin
        # conciliar es dinero que falta: la mayor parte suele estar ya
        # apuntada en el diario (solo falta el click de conciliar) y a veces
        # el feed trae el mismo movimiento dos veces. Solo lo "pendiente de
        # apuntar" suma en la posición; enseñar las tres clases separadas es
        # lo que evita que la 2600 vuelva a salir con 341.943 de más.
        pcl = bk.get("pend_clases") or []
        if pcl:
            t_ap = sum(x["apuntado"] for x in pcl)
            t_du = sum(x["duplicado"] for x in pcl)
            t_pe = sum(x["pendiente"] for x in pcl)
            n_tot = sum(x["n_apuntado"] + x["n_duplicado"] + x["n_pendiente"]
                        for x in pcl)
            def _c(v, n):
                return ('<span class="apagado">—</span>' if n == 0
                        else f'{eur(v)} <span class="apagado">({n})</span>')
            f_cl = [[esc(x["cuenta"]),
                     _c(x["apuntado"], x["n_apuntado"]),
                     _c(x["duplicado"], x["n_duplicado"]),
                     _c(x["pendiente"], x["n_pendiente"])]
                    for x in pcl]
            f_cl.append([f'<b>Total ({n_tot} movs.)</b>',
                         f'<b>{eur(t_ap)}</b>', f'<b>{eur(t_du)}</b>',
                         f'<b>{eur(t_pe)}</b>'])
            t_puente += (
                f'<div class="nota-cuadre {"mal" if abs(t_pe) > 1000 else "ok"}" '
                f'style="margin-top:14px">'
                f'<b>SIN CONCILIAR EN HOLDED: {n_tot} MOVIMIENTOS</b> — la '
                f'posición no depende de esto (sale del banco), pero sí el '
                f'trabajo de contabilidad. <b>Ya apuntado en el diario</b> '
                f'{eur(t_ap)}: existe el asiento, solo falta darle a conciliar. '
                f'<b>Duplicado del feed</b> {eur(t_du)}: el banco lo trae dos '
                f'veces. <b>Pendiente de apuntar de verdad</b> {eur(t_pe)}: '
                f'esto es lo único que le falta al libro diario, y es lo que '
                f'explica la Δ de la tabla de arriba.</div>'
                + tabla(["Cuenta", "Ya apuntado", "Duplicado del feed",
                         "Pendiente de apuntar"],
                        f_cl, alineacion=["", "r", "r", "r"],
                        clases=[""] * (len(f_cl) - 1) + ["total"]))
        des = bk.get("desajuste")
        if des is not None and abs(des) > 1:
            t_puente += (
                f'<div class="nota-cuadre mal" style="margin-top:10px">'
                f'<b>EL SALDO NO CASA CON LOS MOVIMIENTOS POR {eur(des)}</b> — '
                f'el saldo contable del día 1 y el de hoy dicen una variación, '
                f'y sumar los movimientos del banco dice otra. Esa diferencia '
                f'son movimientos que faltan o que están duplicados.</div>')
        elif bk.get("origen_inicio"):
            t_puente += (f'<p class="vacio">Saldo inicial: '
                         f'{esc(bk["origen_inicio"])}.</p>')

        cd = eje.get("contraste_diario")
        if cd is not None:
            ok_cd = abs(cd) <= 1000
            t_puente += (
                f'<div class="nota-cuadre {"ok" if ok_cd else "mal"}" '
                f'style="margin-top:14px">'
                f'<b>{"CONTRASTE OK" if ok_cd else "EL DIARIO NO DICE LO MISMO"}</b>'
                f' — el mismo mes calculado desde el libro diario da una '
                f'diferencia de {eur(cd)} contra el extracto bancario. '
                f'{"Los dos caminos llegan al mismo sitio." if ok_cd else "Hay que mirarlo: o falta un apunte o sobra."}'
                f'</div>')
    elif eje.get("fuente") == "libro diario":
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
    sb = meta.get("serie_fcf") or []
    su = meta.get("serie_unlevered") or []
    if sb:
        # SU SEGUNDO CHECK, mes a mes, con la posicion anclada en tesoreria:
        # el levered (movimiento real del banco) contra lo que el LIBRO
        # DIARIO apunto ese mes. La Δ es lo que la contabilidad todavia no
        # ha recogido: si es grande, alguien va por detras y ya se sabe de
        # cuanto. Antes se comparaba contra el extracto, que ahora es el
        # propio levered y no seria un check sino una identidad.
        def _feed(x):
            f = x.get("diario_neto")
            if f is None:
                return "", ""
            d = x["levered"] - f
            cel_d = (f'<span class="rojo">{eur(d)}</span>' if abs(d) > 1000
                     else f'<span class="chip ok">{eur(d)}</span>')
            return eur(f), cel_d
        f_su = []
        for x in sb:
            fe, fd = _feed(x)
            # LA DEUDA DEL MES, ABIERTA. Cuando el unlevered de un mes se
            # dispara -junio, +1,0M- la explicacion esta siempre aqui: que
            # se ha considerado servicio de deuda. Sin esto hay que creerse
            # la cifra; con esto se discute con nombres y numeros.
            dd = x.get("detalle_deuda") or []
            det = ""
            if dd:
                det = (f'<details><summary>{len(dd)} '
                       f'cuenta{"s" if len(dd) != 1 else ""}</summary>'
                       + tabla(["Cuenta", "Nombre", "Importe"],
                               [[f'<code>{esc(y["cuenta"])}</code>',
                                 esc(y["nombre"] or "deuda"),
                                 f'<span class="{"neg" if y["importe"] < 0 else ""}">'
                                 f'{eur(y["importe"])}</span>'] for y in dd],
                               alineacion=["", "", "r"])
                       + '</details>')
            f_su.append([esc(x["etiqueta"]), eur(x["saldo_inicio"]),
                         eur(x["saldo_hoy"]),
                         f'<span class="{"neg" if x["levered"] < 0 else ""}">'
                         f'{eur(x["levered"])}</span>', fe, fd,
                         f'<span class="{"neg" if x["deuda"] < 0 else ""}">'
                         f'{eur(x["deuda"])}</span>{det}',
                         f'<b><span class="{"neg" if x["unlevered"] < 0 else ""}">'
                         f'{eur(x["unlevered"])}</span></b>'])
        # El agregado es lo que se compara de verdad contra el bottom-up: un
        # mes suelto puede irse por un apunte, el acumulado no.
        tot_feed = sum(x.get("diario_neto") or 0 for x in sb)
        f_su.append([
            f'<b>Acumulado {esc(sb[0]["etiqueta"])} — {esc(sb[-1]["etiqueta"])}</b>',
            f'<b>{eur(sb[0]["saldo_inicio"])}</b>',
            f'<b>{eur(sb[-1]["saldo_hoy"])}</b>',
            f'<b><span class="{"neg" if sum(x["levered"] for x in sb) < 0 else ""}">'
            f'{eur(sum(x["levered"] for x in sb))}</span></b>',
            f'<b>{eur(tot_feed)}</b>',
            f'<b>{eur(sum(x["levered"] for x in sb) - tot_feed)}</b>',
            f'<b><span class="{"neg" if sum(x["deuda"] for x in sb) < 0 else ""}">'
            f'{eur(sum(x["deuda"] for x in sb))}</span></b>',
            f'<b><span class="{"neg" if sum(x["unlevered"] for x in sb) < 0 else ""}">'
            f'{eur(sum(x["unlevered"] for x in sb))}</span></b>'])
        t_serie = tabla(["Mes", "Saldo inicial", "Saldo final", "Levered FCF",
                         "Diario (apuntes)", "Δ sin apuntar", "Pagos de deuda",
                         "Unlevered FCF"], f_su,
                        alineacion=["", "r", "r", "r", "r", "r", "r", "r"],
                        clases=[""] * (len(f_su) - 1) + ["total"])
    elif su:
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
    # Los tres estados que pide Alejandro, como en su fichero de cobros:
    # COBRADO, VENCIDO (deberia estar cobrado segun Eli y no lo esta) y
    # PENDIENTE SIN VENCER (facturado, con la cuota todavia por delante).
    cob_mes = float(cli["cuota_mes"].sum()) if not cli.empty else 0.0
    dc0 = fc.get("detalle_cobros")
    e_cob = None
    tot_cobrado = tot_vencido = tot_sinv = cobrado_mes = 0.0
    if dc0 is not None and not dc0.empty:
        e_cob = dc0.copy()
        e_cob["cobrado"] = e_cob["liquidado"]
        e_cob["vencido_i"] = (e_cob["teorico_hoy"] - e_cob["liquidado"]).clip(lower=0)
        e_cob["sin_vencer"] = (e_cob["total"]
                               - e_cob[["teorico_hoy", "liquidado"]].max(axis=1)
                               ).clip(lower=0)
        tot_cobrado = float(e_cob["cobrado"].sum())
        tot_vencido = float(e_cob["vencido_i"].sum())
        tot_sinv = float(e_cob["sin_vencer"].sum())
    rea0 = meta.get("realizados")
    if rea0 is not None and not rea0.empty:
        cobrado_mes = float(rea0[rea0["sentido"] == "cobro"]["importe"].sum())
    kpis_cob = "".join([
        kpi("Cobrado", eur(tot_cobrado),
            f"{eur(cobrado_mes)} en {m0['etiqueta']}", "ok"),
        kpi("Pendiente vencido", eur(tot_vencido),
            "debería estar cobrado según Eli y no lo está",
            "aviso" if tot_vencido > 300_000 else ""),
        kpi("Pendiente sin vencer", eur(tot_sinv),
            "facturado, con la cuota aún por delante"),
        kpi(f"Cuota teórica de {m0['etiqueta']}", eur(cob_mes),
            "según calendario de Eli"),
    ])

    n_prov = int((prov["pendiente_total"].abs() > 0.01).sum()) if not prov.empty else 0
    n_venc = int((prov["vencido"] > 0.01).sum()) if not prov.empty else 0
    pend_prov = float(prov["pendiente_total"].sum()) if not prov.empty else 0.0
    pagado_mes = 0.0
    if rea0 is not None and not rea0.empty:
        pagado_mes = float(rea0[rea0["sentido"] == "pago"]["importe"].sum())
    kpis_pag = "".join([
        kpi(f"Pagado en {m0['etiqueta']}", eur(pagado_mes),
            "apuntes de liquidación ligados a factura"),
        kpi("Vencido y sin pagar", eur(-vencido), f"{n_venc} proveedores",
            "aviso" if vencido > 200_000 else ""),
        kpi("Pendiente sin vencer", eur(-(pend_prov - vencido)),
            "facturado, con el vencimiento por delante"),
        kpi(f"Pago previsto {m0['etiqueta']}", eur(m0["pago_proveedores"]),
            "vencimientos hasta fin de mes"),
    ])

    # ---- detalle factura a factura, como el fichero de cobros ------------
    # Cada factura cruzada con lo que Eli dice que deberia llevar cobrado.
    # La diferencia es lo VENCIDO; el resto del importe, pendiente SIN VENCER.
    # Sin columnas de teoricos futuros: eso ya lo cuenta el forecast.
    grupos_cob = []
    if e_cob is not None and not e_cob.empty:
        act = e_cob[(e_cob["vencido_i"] > 0.01) | (e_cob["sin_vencer"] > 0.01)]
        for cliente, g in act.groupby("cliente"):
            g = g.sort_values("vencido_i", ascending=False)
            venc, sinv = g["vencido_i"].sum(), g["sin_vencer"].sum()
            resumen = ((f'<span class="rojo"><b>{eur(venc)}</b> vencido</span>'
                        if venc > 0.01 else '<span class="chip ok">al día</span>')
                       + (f' · {eur(sinv)} sin vencer' if sinv > 0.01 else ''))
            filas = [[esc(r["num"]), esc(str(r["vencimiento"] or "—")),
                      eur(r["total"]), eur(r["teorico_hoy"]),
                      eur(r["cobrado"]),
                      (f'<span class="rojo"><b>{eur(r["vencido_i"])}</b></span>'
                       if r["vencido_i"] > 0.01 else "—"),
                      eur(r["sin_vencer"]) if r["sin_vencer"] > 0.01 else "—"]
                     for _, r in g.iterrows()]
            grupos_cob.append((cliente, resumen, filas))
        grupos_cob = sorted(
            grupos_cob,
            key=lambda x: -act[act["cliente"] == x[0]]["vencido_i"].sum())
    cab_cob = ["Factura", "Vencimiento", "Total", "Debería cobrado (Eli)",
               "Cobrado", "Vencido", "Sin vencer"]
    det_cobros = detalle_desplegable(grupos_cob, cab_cob,
                                     alineacion=["", "", "r", "r", "r", "r", "r"],
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

    # ---- calendario de pagos del mes -------------------------------------
    # Lo que pide Alejandro: ver COMO EN UN CALENDARIO que dias pago y que
    # facturas, y que vence cada dia. Un dia con movimiento se pincha y ensena
    # sus facturas debajo; nada de listas kilometricas.
    y_cal, m_cal = int(meses[0][:4]), int(meses[0][4:])
    pag_dia, ven_dia = {}, {}
    if rea is not None and not rea.empty:
        for _, r in rea[rea["sentido"] == "pago"].iterrows():
            f = r["fecha"]
            if getattr(f, "year", None) == y_cal and f.month == m_cal:
                pag_dia.setdefault(f.day, []).append(
                    (str(r["tercero"]), str(r["num"] or r["concepto"] or "")[:36],
                     float(r["importe"])))
    ven_antes = 0.0
    if dp is not None and not dp.empty:
        for _, r in dp[dp["pendiente"] > 0.01].iterrows():
            v = r["vencimiento"]
            if not v or not hasattr(v, "year"):
                continue
            if (v.year, v.month) == (y_cal, m_cal):
                ven_dia.setdefault(v.day, []).append(
                    (str(r["proveedor"]), str(r["num"])[:36], float(r["pendiente"])))
            elif v < date(y_cal, m_cal, 1):
                ven_antes += float(r["pendiente"])

    _hoy = date.today()
    hoy_d = _hoy.day if (_hoy.year, _hoy.month) == (y_cal, m_cal) else None
    celdas, cal_dets = [], []
    for semana in _callib.Calendar(firstweekday=0).monthdayscalendar(y_cal, m_cal):
        fila = []
        for d in semana:
            if d == 0:
                fila.append('<td class="cal off"></td>')
                continue
            p = sum(x[2] for x in pag_dia.get(d, []))
            v = sum(x[2] for x in ven_dia.get(d, []))
            cls = "cal" + (" tiene" if (pag_dia.get(d) or ven_dia.get(d)) else "") \
                  + (" hoy" if d == hoy_d else "")
            cuerpo = f'<div class="cal-num">{d}</div>'
            if abs(p) > 0.005:
                cuerpo += f'<div class="cal-p">{eur(p)}</div>'
            if v > 0.005:
                cuerpo += f'<div class="cal-v">vence {eur(v)}</div>'
            clic = f' onclick="caldia({d})"' if (pag_dia.get(d) or ven_dia.get(d)) else ""
            fila.append(f'<td id="calc{d}" class="{cls}"{clic}>{cuerpo}</td>')
            if pag_dia.get(d) or ven_dia.get(d):
                filas_d = ([[esc(t), esc(n), "pagado",
                             f'<span class="neg">{eur(i)}</span>']
                            for t, n, i in sorted(pag_dia.get(d, []), key=lambda x: x[2])]
                           + [[esc(t), esc(n), "vence", eur(i)]
                              for t, n, i in sorted(ven_dia.get(d, []),
                                                    key=lambda x: -x[2])])
                cal_dets.append(
                    f'<div id="cald{d}" class="cal-det" hidden>'
                    f'<h2 style="font-size:14px;margin:14px 0 6px">'
                    f'Día {d} de {esc(m0["etiqueta"])}</h2>'
                    + tabla(["Tercero", "Factura", "", "Importe"], filas_d,
                            alineacion=["", "", "", "r"]) + '</div>')
        celdas.append("<tr>" + "".join(fila) + "</tr>")
    cal_html = ('<table class="calend"><thead><tr>'
                + "".join(f"<th>{x}</th>" for x in
                          ["L", "M", "X", "J", "V", "S", "D"])
                + '</tr></thead><tbody>' + "".join(celdas) + '</tbody></table>')
    cal_dets_html = "".join(cal_dets)
    nota_ven_antes = (f' Arrastrado de meses anteriores y aún sin pagar: '
                      f'<b>{eur(-ven_antes)}</b>.' if ven_antes > 0.01 else "")

    # ---- el mes en curso: ejecutado + pendiente = proyectado --------------
    # La hoja "Forecast Caja - Mes en Curso" del Excel de Alejandro, que es
    # como el trabaja: cada linea con lo ya ejecutado, lo pendiente y la suma.
    t_mes_curso = ""
    mec = meta.get("mes_en_curso")
    if mec:
        def _n(v, negativo=False):
            if abs(v) < 0.005:
                return '<span class="apagado">—</span>'
            cl = ' class="neg"' if v < 0 else ""
            return f"<span{cl}>{eur(v)}</span>"

        def bloque_mc(titulo, filas, ej, pd_, tot_):
            out = [f'<tr class="sub"><td><b>{titulo}</b></td>'
                   f'<td class="r"><b>{eur(ej)}</b></td>'
                   f'<td class="r"><b>{eur(pd_)}</b></td>'
                   f'<td class="r"><b>{eur(tot_)}</b></td></tr>']
            for f in filas:
                if (abs(f["ejecutado"]) < 0.005 and abs(f["pendiente"]) < 0.005):
                    continue
                out.append(
                    f'<tr><td style="padding-left:22px">{esc(f["concepto"])}</td>'
                    f'<td class="r">{_n(f["ejecutado"])}</td>'
                    f'<td class="r">{_n(f["pendiente"])}</td>'
                    f'<td class="r">{_n(f["total"])}</td></tr>')
            return "".join(out)

        t = mec["tot"]
        fd = mec["deuda"]
        cn = mec["concil"]
        cuadra_cn = abs(cn["descuadre"]) <= max(cn["tolerancia"], 1.0)
        cuerpo = (
            bloque_mc("CASH IN", mec["cash_in"], t["in_ej"], t["in_pd"], t["in_tot"])
            + bloque_mc("CASH OUT (sin deuda)", mec["cash_out"],
                        t["out_ej"], t["out_pd"], t["out_tot"])
            + f'<tr class="total"><td><b>UNLEVERED FCF</b></td>'
              f'<td class="r"><b>{eur(t["unlev_ej"])}</b></td>'
              f'<td class="r"><b>{eur(t["unlev_pd"])}</b></td>'
              f'<td class="r"><b>{eur(t["unlev_tot"])}</b></td></tr>'
            + f'<tr><td style="padding-left:22px">{esc(fd["concepto"])} '
              f'<i>(pendiente del mes no proyectado)</i></td>'
              f'<td class="r">{_n(fd["ejecutado"])}</td>'
              f'<td class="r"><span class="apagado">—</span></td>'
              f'<td class="r">{_n(fd["total"])}</td></tr>'
            + f'<tr class="total"><td><b>LEVERED FCF</b> = variación de caja</td>'
              f'<td class="r"><b>{eur(t["lev_ej"])}</b></td>'
              f'<td class="r"><b>{eur(t["lev_pd"])}</b></td>'
              f'<td class="r"><b>{eur(t["lev_tot"])}</b></td></tr>')
        chip_cn = ('<span class="chip ok">cuadra</span>' if cuadra_cn else
                   f'<span class="chip crit">{eur(cn["descuadre"])} sin explicar</span>')
        t_mes_curso = f'''
  <section>
    <h2>{esc(mec["etiqueta"])} — ejecutado, pendiente y proyectado</h2>
    <p class="h2n">Como tu hoja «Forecast Caja - Mes en Curso»: lo ya ejecutado
     (libro diario, cada euro en una sola línea por contrapartida), lo
     pendiente según el forecast, y la suma. El UNLEVERED arriba, la deuda
     debajo, y el LEVERED tiene que cuadrar con la variación de las cuentas
     bancarias. {chip_cn}</p>
    <table>
      <thead><tr><th>Concepto</th><th class="r">Ejecutado</th>
      <th class="r">Pendiente</th><th class="r">Mes proyectado</th></tr></thead>
      <tbody>{cuerpo}</tbody>
    </table>
    <table style="margin-top:12px;max-width:640px">
      <thead><tr><th>El levered, contra los bancos</th><th class="r">Importe</th></tr></thead>
      <tbody>
        <tr><td>LEVERED ejecutado = variación contable de bancos</td>
            <td class="r">{eur(cn["contable"])}</td></tr>
        <tr><td>Pendiente de conciliar del mes (extracto, con signo)</td>
            <td class="r">{eur(cn["pendiente"])}</td></tr>
        <tr><td>Descuadre restante</td>
            <td class="r"><span class="{"" if cuadra_cn else "rojo"}">{eur(cn["descuadre"])}</span></td></tr>
        <tr class="total"><td><b>= Variación de saldos bancarios (día 1 → hoy)</b></td>
            <td class="r"><b>{eur(cn["saldos"])}</b></td></tr>
      </tbody>
    </table>
    <p class="h2n" style="margin-top:10px">Saldo hoy {eur(mec["saldo_hoy"])} +
     pendiente {eur(t["lev_pd"])} = <b>saldo proyectado a cierre
     {eur(mec["saldo_cierre"])}</b>.</p>
  </section>'''

    # la pantalla de la reunion: primera pestana, una sola pregunta
    t_nacho = pantalla_nacho(meta.get("resumen_nacho"), fc, meta)
    if not t_nacho:
        t_nacho = ('<p class="vacio">Sin datos suficientes para el resumen '
                   'de reunión: hace falta el extracto bancario.</p>')

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

    # ---- actualizar sin salir del panel -----------------------------------
    # El boton lanza el workflow directamente contra la API de GitHub y va
    # contando el estado hasta recargar solo. La pieza delicada es la llave:
    # una pagina publica NO puede llevar el token dentro -seria regalarlo a
    # cualquiera que abra el HTML-, asi que el token vive unicamente en el
    # navegador de Alejandro (localStorage). La primera vez el panel se lo
    # pide; el lo crea en GitHub con el permiso minimo (Actions: write sobre
    # este repo y nada mas: no puede tocar codigo) y lo pega. Nunca viaja al
    # repo ni a la pagina publicada.
    m_wf = re.match(r"https://github\.com/([^/]+)/([^/]+)/actions/workflows/(.+)$",
                    url_workflow or "")
    js_actualizar = ""
    btn_actualizar = (f'<a class="btn-refresh" href="{url_workflow}" '
                      f'target="_blank" rel="noopener">⟳ Forzar actualización</a>')
    if m_wf:
        api_wf = (f"https://api.github.com/repos/{m_wf.group(1)}/{m_wf.group(2)}"
                  f"/actions/workflows/{m_wf.group(3)}")
        btn_actualizar = (
            '<button class="btn-refresh" id="btnRef" onclick="forzar()" '
            'title="Lanza la extracción de Holded y recarga el panel al terminar">'
            '⟳ Actualizar</button>'
            '<span id="refEstado" class="ref-estado"></span>')
        panel_token = f'''
<div id="refConf" class="ref-conf" hidden>
  <b>Un paso, solo la primera vez.</b>
  <p>Para que este botón funcione sin pasar por GitHub hace falta una llave.
  No puede ir dentro de la página —esto es una web pública y sería regalarla—,
  así que se guarda <b>solo en este navegador</b>.</p>
  <ol>
    <li><a href="https://github.com/settings/personal-access-tokens/new"
      target="_blank" rel="noopener">Crea el token aquí</a> (fine-grained):
      <b>Repository access → Only select repositories →
      {esc(m_wf.group(2))}</b>, y en Permissions
      <b>Actions → Read and write</b>. Nada más: esa llave no puede tocar
      el código, solo lanzar actualizaciones.</li>
    <li>Pégalo y guarda:</li>
  </ol>
  <div class="ref-fila">
    <input type="password" id="refTok" placeholder="github_pat_…" autocomplete="off">
    <button class="btn-mini" onclick="guardarToken()">Guardar</button>
    <button class="btn-mini" onclick="cerrarConf()">Cancelar</button>
  </div>
  <p class="apagado">Alternativa de siempre:
  <a href="{url_workflow}" target="_blank" rel="noopener">lanzarlo desde GitHub</a>.
  Si algún día quieres retirar la llave: bórrala en GitHub y aquí con
  <a href="#" onclick="borrarToken();return false">quitar token de este navegador</a>.</p>
</div>'''
        js_actualizar = ('<script>\n'
                         + JS_ACTUALIZAR
                         .replace("__API__", api_wf)
                         .replace("__WFURL__", url_workflow)
                         + '\n</script>')
    else:
        panel_token = ""

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
        # El contraste contra el Excel se retira: "no va a haber mas Excel".
        # Era el puente para la transicion y la transicion ya esta hecha.
        contraste_html = ""
    else:
        contraste_html = ""

    # ---- boton de descarga del Excel --------------------------------------
    # El fichero viaja dentro de la propia pagina (data URI): cada recarga
    # trae el Excel de esa actualizacion, en GitHub Pages, en Cloudflare o
    # abriendo el HTML desde el disco. Sin rutas que se rompan.
    btn_excel = ""
    if meta.get("excel_b64"):
        btn_excel = (
            f'<a class="btn-refresh" download="{esc(meta.get("excel_nombre") or "caja_leaseir.xlsx")}" '
            f'href="data:application/vnd.openxmlformats-officedocument.'
            f'spreadsheetml.sheet;base64,{meta["excel_b64"]}" '
            f'title="Tu fichero de trabajo con los datos de esta actualización: '
            f'Mes en Curso, Bottom Up, Cobros, Pagos y Forecast">⬇ Excel</a>')

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
button.btn-refresh{{border:0;cursor:pointer;font:inherit}}
button.btn-refresh:disabled{{opacity:.55;cursor:wait}}
.ref-estado{{font-size:13px;color:#fff;opacity:.92;display:inline-flex;
 align-items:center;gap:7px}}
.ref-estado a{{color:#fff}}
.spin{{width:12px;height:12px;border:2px solid rgba(255,255,255,.35);
 border-top-color:#fff;border-radius:50%;display:inline-block;
 animation:gira .8s linear infinite}}
@keyframes gira{{to{{transform:rotate(360deg)}}}}
.ref-conf{{max-width:860px;margin:14px auto 0;padding:16px 20px;background:#fff;
 border:1px solid #e3b34c;border-radius:11px;font-size:14px}}
.ref-conf ol{{margin:8px 0 10px 20px;padding:0}}
.ref-conf li{{margin-bottom:6px}}
.ref-fila{{display:flex;gap:8px;align-items:center;flex-wrap:wrap}}
.ref-fila input{{flex:1;min-width:260px;padding:8px 12px;font-size:14px;
 border:1px solid #ccd4dc;border-radius:7px}}
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
th.c,td.c{{text-align:center}}
tr.sub td{{background:#f1f4f5;font-weight:600}}
tr.total td{{background:{P['brand']};color:#fff;font-weight:700}}
tr.total td .neg{{color:#ffc9c9}}
tbody tr:hover td{{background:#f7f9fa}}
tr.sub:hover td,tr.total:hover td{{background:inherit}}
.b{{font-weight:650}} .neg{{color:{P['crit']}}} .apagado{{color:#c2c8cf}}
.calend{{width:100%;table-layout:fixed;border-collapse:collapse;margin-top:6px}}
.calend th{{font-size:11px;color:#8a94a6;text-align:left;padding:2px 6px;border:none}}
td.cal{{border:1px solid #e8ecf1;vertical-align:top;height:58px;padding:4px 6px;
 font-size:12px;background:#fff}}
td.cal.off{{background:#fafbfc;border-color:#f0f2f5}}
td.cal.tiene{{cursor:pointer}}
td.cal.tiene:hover{{background:#f4f7fb}}
td.cal.hoy{{outline:2px solid {P['brand']};outline-offset:-2px}}
td.cal.sel{{background:#eef4ff}}
.cal-num{{font-weight:700;color:#8a94a6;font-size:11px}}
.cal-p{{color:{P['crit']};font-weight:700;white-space:nowrap}}
.cal-v{{color:#8a5d00;white-space:nowrap}}
.chip{{display:inline-block;padding:1px 8px;border-radius:20px;font-size:12px;font-weight:600}}
.chip.ok{{background:#e6f5e6;color:{P['up']}}}
.chip.warn{{background:#fdf1d8;color:#8a5d00}}
.chip.crit{{background:#fbe6e6;color:#a32020}}
tr.res td{{background:#fbe6e6}}
details.aud{{margin:26px 0;border:1px dashed #c7d0d9;border-radius:11px;
 padding:4px 18px;background:#fbfcfd}}
details.aud>summary{{cursor:pointer;font-size:14px;font-weight:600;
 color:#5a6a78;padding:10px 0}}
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
/* ---- LA PANTALLA DE NACHO: cabe entera, sin scroll --------------------
   Se dimensiona con la altura de la ventana (dvh, que en movil descuenta
   la barra del navegador) y las tres filas reparten lo que quede. Si la
   pantalla es pequena de verdad, se deja fluir en vez de recortar: mejor
   scroll que un numero cortado por la mitad. */
/* La altura no se calcula restando constantes -el header cambia de alto
   segun haya banner o no-: la pagina entera se vuelve una columna flex de
   una ventana de alto y la pantalla se queda con lo que sobre. */
body.reunion .wrap{{display:flex;flex-direction:column;min-height:100dvh;
 padding-bottom:0}}
body.reunion .pie{{display:none}}
body.reunion #p0.panel.visible{{display:flex;flex-direction:column;
 flex:1 1 auto;min-height:0}}
.nacho{{display:flex;flex-direction:column;gap:10px;flex:1 1 auto;
 min-height:500px}}
.nacho .chart{{margin:0;flex:1 1 auto;min-height:0}}
@media(max-width:900px){{.nacho{{min-height:0}}}}
 .bleg{{font-size:11.5px}}
}}
.nq{{border-radius:12px;padding:12px 18px;display:grid;
 grid-template-columns:1fr auto;align-items:center;gap:4px 20px;flex:0 0 auto}}
.nq-p{{font-size:13px;font-weight:600;opacity:.75;grid-column:1}}
.nq-r{{font-size:30px;font-weight:800;letter-spacing:-.5px;grid-row:1/3;
 grid-column:2;text-align:right;line-height:1.05}}
.nq-s{{font-size:13.5px;grid-column:1;line-height:1.45}}
.nq.si{{background:#e6f5e6;color:#0d5c0d}}
.nq.justo{{background:#fdf4e2;color:#7a5200}}
.nq.no{{background:#fbe6e6;color:#8f1d1d}}
.nkpis{{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;flex:0 0 auto}}
.nk{{background:{P['surface']};border:1px solid {P['border']};border-radius:11px;
 padding:10px 13px;border-top:3px solid {P['brand']};min-width:0}}
.nk.malo{{border-top-color:{P['crit']}}}
.nk.malo .nk-v{{color:{P['crit']}}}
.nk-t{{font-size:11.5px;color:{P['ink2']};font-weight:600;line-height:1.25;
 min-height:29px}}
.nk-v{{font-size:25px;font-weight:800;letter-spacing:-.6px;margin:3px 0 2px;
 font-variant-numeric:tabular-nums;white-space:nowrap}}
.nk-n{{font-size:11px;color:{P['muted']};line-height:1.35}}
.mas{{appearance:none;border:0;background:none;color:{P['s1']};font-weight:700;
 font-size:11px;cursor:pointer;padding:0 0 0 4px;font-family:inherit}}
.mas:hover{{text-decoration:underline}}
.ngrid{{display:grid;grid-template-columns:repeat(3,1fr);
 grid-template-rows:1fr auto;gap:10px;flex:1 1 auto;min-height:0}}
.ncard{{background:{P['surface']};border:1px solid {P['border']};border-radius:11px;
 padding:9px 13px 6px;min-width:0;overflow:hidden;display:flex;
 flex-direction:column}}
.ncard.ancho{{grid-column:1/-1}}
.ncard h3{{font-size:12px;margin:0 0 4px;color:{P['ink2']};font-weight:700}}
.ncard .nn2{{font-weight:500;color:{P['muted']}}}
.ncard table{{margin:0;font-size:12px}}
.ncard td,.ncard th{{padding:3px 6px}}
.nn{{font-size:11px;color:{P['muted']};margin:5px 0 0;line-height:1.4}}
.bstack{{display:flex;height:26px;border-radius:6px;overflow:hidden;margin:6px 0 7px}}
.bstack i{{display:block}}
.bleg{{display:flex;gap:18px;flex-wrap:wrap;font-size:12px;color:{P['ink2']}}}
.bleg span{{display:flex;align-items:center;gap:6px}}
.bleg i{{width:10px;height:10px;border-radius:3px;display:inline-block}}
.bleg.map{{margin-top:7px;font-size:11.5px;color:{P['muted']}}}
.modal{{position:fixed;inset:0;background:rgba(20,22,24,.45);z-index:60;
 display:none;align-items:center;justify-content:center;padding:24px}}
.modal.abierto{{display:flex}}
.mbox{{background:#fff;border-radius:13px;padding:20px 24px;max-width:900px;
 width:100%;max-height:82vh;overflow:auto;position:relative}}
.mbox h3{{margin:0 0 12px;font-size:16px;color:{P['brand']}}}
.mx{{position:absolute;top:12px;right:16px;appearance:none;border:0;
 background:none;font-size:26px;line-height:1;color:{P['muted']};cursor:pointer}}
/* En un portatil de 768 de alto todo se compacta un punto antes que
   aparezca el scroll: mejor apretado que partido en dos pantallas. */
@media(max-height:860px){{
 .nacho{{gap:8px;min-height:0}}
 .nq{{padding:9px 16px}} .nq-p{{font-size:12px}} .nq-r{{font-size:25px}}
 .nq-s{{font-size:12.5px}}
 .nk{{padding:8px 11px}} .nk-t{{font-size:11px;min-height:26px}}
 .nk-v{{font-size:21px}} .nk-n{{font-size:10.5px}}
 .ncard{{padding:7px 11px 5px}} .ncard table{{font-size:11.5px}}
 .ncard td,.ncard th{{padding:2px 5px}}
 .bstack{{height:20px;margin:4px 0 5px}} .bleg{{font-size:11.5px;gap:14px}}
 .bleg.map{{margin-top:5px;font-size:11px}}
 .nn{{font-size:10.5px;line-height:1.3;margin-top:4px}}
 .nq-p{{margin-bottom:1px}}
 /* la cabecera tambien cede: en la reunion lo que importa es el numero,
    no el logo. Solo en la pestana de reunion y solo si hace falta. */
 body.reunion .marca{{padding:12px 20px}}
 body.reunion .wordmark{{font-size:21px;letter-spacing:5px}}
 body.reunion .claim{{font-size:9.5px}}
 body.reunion .doc{{font-size:14px}} body.reunion .doc2{{font-size:11px}}
 body.reunion .tira{{padding:6px 20px;margin-bottom:14px}}
 body.reunion .tabs{{margin-bottom:12px}}
 body.reunion .tab{{padding:8px 14px;font-size:13.5px}}
}}
@media(max-height:745px){{
 .nacho{{gap:6px}}
 .nq{{padding:7px 14px}} .nq-r{{font-size:22px}} .nq-s{{font-size:12px}}
 .nk{{padding:6px 10px}} .nk-t{{font-size:10.5px;min-height:24px}}
 .nk-v{{font-size:19px;margin:2px 0 1px}}
 .ncard{{padding:6px 10px 4px}} .ncard h3{{font-size:11.5px;margin-bottom:2px}}
 .ngrid{{gap:8px}}
}}
.tabs{{display:flex;gap:6px;margin:0 0 20px;border-bottom:2px solid {P['grid']}}}
.tab{{appearance:none;background:none;border:0;border-bottom:3px solid transparent;
 margin-bottom:-2px;padding:11px 18px;font-size:14.5px;font-weight:600;
 color:{P['muted']};cursor:pointer;font-family:inherit;transition:color .12s}}
.tab:hover{{color:{P['ink2']}}}
.tab.activa{{color:{P['brand']};border-bottom-color:{P['brand']}}}
.panel{{display:none}}
.panel.visible{{display:block}}
.edit-bar{{margin:14px 0 4px;padding:10px 14px;background:#f4f7fb;border-radius:9px;
 font-size:14px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}}
.edit-bar b{{font-size:16px}}
.btn-mini{{margin-left:auto;padding:6px 12px;font-size:13px;font-weight:600;
 border:1px solid {P['brand']};background:#fff;color:{P['brand']};
 border-radius:7px;cursor:pointer}}
.btn-mini:hover{{background:{P['brand']};color:#fff}}
#cobYaml{{background:#141618;color:#d6e4dd;padding:14px;border-radius:9px;
 font-size:12px;overflow-x:auto;margin-top:8px}}
.cbi{{width:104px;padding:3px 6px;font-size:13px;text-align:right;
 border:1px solid #ccd4dc;border-radius:6px}}
td .cbx{{transform:scale(1.15)}}
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
table.fc{{width:100%;border-collapse:collapse;font-size:13.5px;
 font-variant-numeric:tabular-nums}}
table.fc th{{text-align:left;font-size:10.5px;text-transform:uppercase;
 letter-spacing:.5px;color:{P['brand']};font-weight:700;padding:8px 10px;
 border-bottom:1.5px solid {P['brand']};white-space:nowrap}}
table.fc th.r,table.fc td.r{{text-align:right}}
table.fc td{{padding:7px 10px;border-bottom:1px solid {P['grid']}}}
table.fc tr.sub td{{background:#f1f4f5;font-weight:600}}
table.fc tr.total td{{background:{P['brand']};color:#fff;font-weight:700}}
table.fc tr.total td .neg{{color:#ffc9c9}}
tr.desplegable{{cursor:pointer}}
tr.desplegable:hover td{{background:#f7f9fa}}
tr.desplegable.total:hover td{{background:{P['brand']}}}
.abre{{display:inline-block;width:14px;color:{P['muted']};font-size:10px;
 transition:transform .12s}}
.abre.vacia{{color:transparent}}
tr.abierta .abre{{transform:rotate(90deg)}}
tr.fc-det>td{{padding:0 10px 12px 24px;background:#fbfcfc}}
tr.fc-det table{{font-size:11.5px;margin-top:2px}}
tr.fc-det td{{padding:4px 8px}}
tr.fc-det th{{padding:5px 8px;font-size:9.5px}}
.pie{{margin:30px -20px -72px;padding:20px;background:{P['brand']};color:#a9c4ce;
 font-size:11.5px;line-height:1.65;display:flex;justify-content:space-between;
 gap:24px;flex-wrap:wrap}}
.pie b{{color:#fff;letter-spacing:1.5px}}
.pie-r{{max-width:660px;text-align:right}}
code{{background:#eef1f2;padding:1px 5px;border-radius:3px;font-size:12.5px}}
</style></head>
<body class="reunion"><div class="wrap">

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
  {btn_actualizar}
  {btn_excel}
</div>

{panel_token}

{banner}

<nav class="tabs">
  <button class="tab activa" data-p="p0">Reunión · 1 pantalla</button>
  <button class="tab" data-p="p1">Forecast de caja</button>
  <button class="tab" data-p="p2">Cobros</button>
  <button class="tab" data-p="p3">Pagos</button>
</nav>

<div id="p0" class="panel visible">{t_nacho}</div>

<div id="p1" class="panel">

  <div class="kpis">{kpis}</div>

  {t_mes_curso}

  <section>
    <h2>El check: variación de bancos = cobros + pagos</h2>
    <p class="h2n"><b>Inicio</b> y <b>Hoy</b> son <b>tesorería</b>: el saldo
     que hay hoy en el banco y ese mismo saldo andado hacia atrás con los
     movimientos del extracto. Al banco le da igual si el apunte está hecho,
     y siempre habrá cosas sin conciliar. La variación ES el levered.
     Contabilidad va al lado, como contraste: la <b>Δ</b> de cada cuenta es
     lo que le falta por apuntar o conciliar, y ahí es donde hay trabajo, no
     en la posición. El día que tengas el extracto real de fin de mes,
     escríbelo en <code>tesoreria.saldos_apertura</code> y manda él.</p>
    {t_puente}
  </section>

  <section>
    <h2>Forecast de caja</h2>
    <p class="h2n">Las líneas con ▸ se abren y enseñan de qué se componen. Los pagos
     a proveedor arrastran los vencidos al mes en curso.</p>
    {tabla_fc}
  </section>

  <section>
    <h2>Previsiones: lo que de verdad se va a cobrar y pagar</h2>
    <p class="h2n">Correcciones manuales sobre lo que proyecta el motor. Holded
     no sabe que un cliente no va a pagar este mes; tú sí.</p>
    {t_prev}
  </section>

  <section>
    <h2>Posición bancaria</h2>
    {t_ban}
  </section>

  <details class="aud"><summary>Auditoría: series, cuadres internos y gráficos</summary>
  <section>
    <h2>Evolución de la caja</h2>
    <p class="h2n">Saldo de partida, flujo libre de cada mes y saldo al final del horizonte.</p>
    {wf}
    <div style="margin-top:18px">{lg_mes}{barras_mes}</div>
  </section>
  <section>
    <h2>Check de la proyección</h2>
    <p class="h2n">Saldo inicial + cash in + cash out = saldo final, mes a mes.</p>
    {cuadre_proy}
    <h2 style="font-size:15px;margin-top:24px">Cuadre contra el banco</h2>
    {cuadre_html}
  </section>
  <section>
    <h2>Unlevered ejecutado de los meses cerrados</h2>
    <p class="h2n">La misma cuenta, mes a mes, para contrastar contra el
     bottom-up sin discutir una sola cifra.</p>
    {t_serie}
  </section>
  {contraste_html}
  </details>

  <section>
    <h2>Calidad del dato</h2>
    <p class="h2n">Incidencias detectadas al construir el forecast.</p>
    {dq_html}
  </section>

</div>

<div id="p2" class="panel">

  <div class="kpis">{kpis_cob}</div>

  {t_cobrab}

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
    <h2>Calendario de pagos de {etiqueta_m0}</h2>
    <p class="h2n">En rojo lo pagado cada día; en ámbar lo que vence y sigue sin
     pagar. Pincha un día para ver sus facturas.{nota_ven_antes}</p>
    {cal_html}
    {cal_dets_html}
    <details><summary>Todos los apuntes de pago del mes — {tot_pag_hechos} en
     {n_pag_hechos} apunte{s_pag}</summary>
      <div class="buscador">
        <input type="text" id="bph" placeholder="Filtrar proveedor…" oninput="filtrar('p3h', this.value)">
      </div>
      <div id="p3h" class="detalles">{det_pag_hechos}</div>
    </details>
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
var MES_ACTUAL = "{m0['mes']}";

// Las ventanas de la pantalla de reunion. El detalle se abre ENCIMA, nunca
// empujando la pagina: si la pantalla creciera, dejaria de caber en una.
document.querySelectorAll('.mas').forEach(function (b) {{
  b.addEventListener('click', function () {{
    var m = document.getElementById(b.dataset.m);
    if (m) m.classList.add('abierto');
  }});
}});
function cerrarModales() {{
  document.querySelectorAll('.modal').forEach(function (m) {{
    m.classList.remove('abierto');
  }});
}}
document.querySelectorAll('.mx').forEach(function (b) {{
  b.addEventListener('click', cerrarModales);
}});
document.querySelectorAll('.modal').forEach(function (m) {{
  m.addEventListener('click', function (e) {{ if (e.target === m) cerrarModales(); }});
}});
document.addEventListener('keydown', function (e) {{
  if (e.key === 'Escape') cerrarModales();
}});

document.querySelectorAll('.tab').forEach(function (b) {{
  b.addEventListener('click', function () {{
    document.querySelectorAll('.tab').forEach(function (x) {{ x.classList.remove('activa'); }});
    document.querySelectorAll('.panel').forEach(function (x) {{ x.classList.remove('visible'); }});
    b.classList.add('activa');
    document.getElementById(b.dataset.p).classList.add('visible');
    document.body.classList.toggle('reunion', b.dataset.p === 'p0');
    window.scrollTo({{ top: 0, behavior: 'smooth' }});
  }});
}});

// Cada linea del cuadro con desglose abre su detalle justo debajo, en el
// mismo sitio donde esta el numero.
document.querySelectorAll('tr.desplegable').forEach(function (tr) {{
  tr.addEventListener('click', function () {{
    var d = document.getElementById(tr.dataset.det);
    if (!d) return;
    d.hidden = !d.hidden;
    tr.classList.toggle('abierta', !d.hidden);
  }});
}});

function filtrar(id, q) {{
  var t = (q || '').toLowerCase();
  document.getElementById(id).querySelectorAll('details.terc').forEach(function (d) {{
    var n = d.querySelector('.t-nom').textContent.toLowerCase();
    d.style.display = n.indexOf(t) === -1 ? 'none' : '';
  }});
}}
function caldia(d) {{
  var det = document.getElementById('cald' + d);
  var abierto = det && !det.hidden;
  document.querySelectorAll('.cal-det').forEach(function (x) {{ x.hidden = true; }});
  document.querySelectorAll('td.cal.sel').forEach(function (x) {{ x.classList.remove('sel'); }});
  if (det && !abierto) {{
    det.hidden = false;
    var c = document.getElementById('calc' + d);
    if (c) c.classList.add('sel');
  }}
}}
function eurJs(v) {{
  return Math.round(v).toLocaleString('es-ES') + ' €';
}}
function recalcCob() {{
  var tot = 0;
  document.querySelectorAll('.cbx').forEach(function (c) {{
    if (!c.checked) return;
    var i = document.querySelector('.cbi[data-k="' + c.dataset.k + '"]');
    tot += parseFloat((i && i.value) || 0);
  }});
  var e = document.getElementById('cobEd');
  if (e) e.textContent = eurJs(tot);
}}
function yamlCob() {{
  var out = [];
  document.querySelectorAll('.cbx').forEach(function (c) {{
    var i = document.querySelector('.cbi[data-k="' + c.dataset.k + '"]');
    var imp = c.checked ? parseFloat((i && i.value) || 0) : 0;
    var def = parseFloat(c.dataset.def || 0);
    if (Math.abs(imp - def) > 0.5) {{
      out.push('  - {{ tipo: cobro, clave: "' + c.dataset.num + '", mes: ' + MES_ACTUAL
               + ', importe: ' + Math.round(imp) + ', nota: "editado en el panel" }}');
    }}
  }});
  var txt = out.length ? 'previsiones:\\n' + out.join('\\n')
                       : '# tu edicion coincide con el motor: no hace falta ninguna prevision';
  var pre = document.getElementById('cobYaml');
  pre.hidden = false;
  pre.textContent = txt + '\\n\\n# Pegalo en la seccion previsiones de config.yaml y sube el fichero:\\n# la siguiente actualizacion lo aplicara y lo dejara trazado en el panel.';
  if (navigator.clipboard) navigator.clipboard.writeText(txt).catch(function () {{}});
}}
</script>
{js_actualizar}
</body></html>"""
