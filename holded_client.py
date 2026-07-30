# -*- coding: utf-8 -*-
"""
============================================================================
 LEASEIR - Cliente de la API de Holded
============================================================================
 Escrito a prueba de sorpresas, porque la API de Holded no es homogenea:
 conviven formatos de token distintos, no todos los endpoints aceptan los
 mismos parametros y algunos tipos de documento no existen en todas las
 cuentas.

 Reglas de diseno, aprendidas del run #1 (que devolvio HTTP 400):

  1. Un 400 NO significa token invalido. Significa peticion mal formada.
     Solo un 401 o un 403 hablan de credenciales.
  2. La sonda de autenticacion prueba cabeceras Y endpoints. Si solo se
     prueba un endpoint y resulta que ese endpoint no existe, se concluye
     erroneamente que la culpa es del token.
  3. Un bloque que falla no tumba la extraccion entera: se avisa, se deja
     vacio y se sigue. Perder los abonos no debe impedir traer las facturas.
  4. La paginacion se corta tambien por repeticion: si un endpoito ignora
     el parametro 'page', devolveria lo mismo indefinidamente.
============================================================================
"""
from __future__ import annotations

import time
from datetime import datetime, date, timezone

import requests

BASE_INVOICING = "https://api.holded.com/api/invoicing/v1"
BASE_ACCOUNTING = "https://api.holded.com/api/accounting/v1"
TIMEOUT = 60
PAUSA = 0.30


def ts(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())


class HoldedError(RuntimeError):
    pass


class Holded:
    """Cliente minimo, tolerante y que deja rastro de todo lo que intenta."""

    # (nombre, cabeceras, manda Content-Type en el GET)
    MODOS = [
        ("key",           {"key": "{k}"},                  False),
        ("key+ct",        {"key": "{k}"},                  True),
        ("bearer",        {"Authorization": "Bearer {k}"},  False),
        ("bearer+ct",     {"Authorization": "Bearer {k}"},  True),
        ("x-api-key",     {"X-API-KEY": "{k}"},             False),
        ("x-auth-token",  {"X-AUTH-TOKEN": "{k}"},          False),
        ("apikey",        {"apikey": "{k}"},                False),
    ]

    # Endpoints de sondeo, del mas probable al menos. Se prueban todos porque
    # un 400 puede venir del endpoint y no de la credencial.
    SONDAS = [
        f"{BASE_INVOICING}/contacts",
        f"{BASE_INVOICING}/documents/invoice",
        f"{BASE_INVOICING}/treasury",
        f"{BASE_INVOICING}/customers",
        f"{BASE_INVOICING}/products",
        f"{BASE_INVOICING}/numbering-series",
    ]

    def __init__(self, api_key: str, verboso: bool = True):
        if not api_key:
            raise HoldedError(
                "No hay API key. Define HOLDED_API_KEY en el entorno "
                "(en GitHub va como secret)."
            )
        self.key = api_key.strip()
        self.s = requests.Session()
        self.modo: str | None = None
        self.verboso = verboso
        self.bitacora: list[dict] = []

    # -----------------------------------------------------------------------
    def _cab(self, modo: str) -> dict:
        for nombre, plantilla, con_ct in self.MODOS:
            if nombre == modo:
                h = {"Accept": "application/json",
                     "User-Agent": "leaseir-control-caja/1.0"}
                if con_ct:
                    h["Content-Type"] = "application/json"
                for c, v in plantilla.items():
                    h[c] = v.format(k=self.key)
                return h
        return {"Accept": "application/json", "key": self.key}

    def _log(self, txt: str) -> None:
        if self.verboso:
            print(txt, flush=True)

    # -----------------------------------------------------------------------
    def autenticar(self) -> str:
        """
        Encuentra la combinacion cabecera/endpoint que Holded acepta.
        Deja en self.bitacora el resultado de cada intento, para que el log del
        workflow sirva de diagnostico sin tener que adivinar.
        """
        if self.modo:
            return self.modo

        self._log("  Sondeando la API de Holded (cabecera x endpoint)")
        self._log(f"  {'cabecera':14s} {'endpoint':34s} codigo  respuesta")
        self._log("  " + "-" * 78)

        vistos_401 = False
        for nombre, _, _ in self.MODOS:
            for url in self.SONDAS:
                corto = url.replace(BASE_INVOICING, "").replace(BASE_ACCOUNTING, "acc:")
                try:
                    r = self.s.get(url, headers=self._cab(nombre), timeout=TIMEOUT)
                except requests.RequestException as e:
                    raise HoldedError(f"Sin conexion con api.holded.com: {e}")

                cuerpo = (r.text or "").strip().replace("\n", " ")[:90]
                self._log(f"  {nombre:14s} {corto:34s} {r.status_code:>6}  {cuerpo}")
                self.bitacora.append({"modo": nombre, "url": corto,
                                      "codigo": r.status_code, "cuerpo": cuerpo})

                if r.status_code == 200:
                    self.modo = nombre
                    self._log("  " + "-" * 78)
                    self._log(f"  [OK] Holded responde con la cabecera '{nombre}' "
                              f"en {corto}")
                    return nombre
                if r.status_code in (401, 403):
                    vistos_401 = True
                time.sleep(0.15)

        detalle = "\n".join(
            f"    {b['modo']:14s} {b['url']:34s} {b['codigo']}  {b['cuerpo']}"
            for b in self.bitacora)
        if vistos_401:
            raise HoldedError(
                "Holded responde 401/403: el token existe pero no tiene permisos.\n"
                "Ve a Holded > Ajustes > Desarrolladores > Credenciales y comprueba\n"
                "que el token tenga LECTURA sobre Facturacion, Contactos, Tesoreria\n"
                "y Contabilidad. Detalle de los intentos:\n" + detalle)
        raise HoldedError(
            "Ninguna combinacion ha devuelto 200, y no hay ningun 401/403, asi que\n"
            "el problema es de formato de peticion o de plan, no de permisos.\n"
            "Detalle de los intentos:\n" + detalle)

    # -----------------------------------------------------------------------
    def get(self, url: str, **params):
        modo = self.autenticar()
        for intento in range(4):
            try:
                r = self.s.get(url, headers=self._cab(modo), params=params,
                               timeout=TIMEOUT)
            except requests.RequestException as e:
                self._log(f"    [aviso] error de red: {e}")
                time.sleep(2 ** intento)
                continue

            if r.status_code == 200:
                try:
                    return r.json()
                except ValueError:
                    self._log(f"    [aviso] {url} no devuelve JSON")
                    return None
            if r.status_code in (429, 500, 502, 503, 504):
                espera = 2 ** intento
                self._log(f"    HTTP {r.status_code}, reintento en {espera}s")
                time.sleep(espera)
                continue
            # 400 / 404: ese endpoint no aplica a esta cuenta. No es fatal.
            self._log(f"    [aviso] HTTP {r.status_code} en {url} "
                      f"-> {(r.text or '')[:140].strip()}")
            return None
        return None

    # -----------------------------------------------------------------------
    def paginar(self, url: str, etiqueta: str = "", **params) -> list:
        """
        Recorre paginas hasta agotar. Corta por lista vacia, por lote corto y
        tambien por repeticion: si el endpoint ignora 'page', devolveria
        siempre lo mismo y entrariamos en bucle.
        """
        salida, vistos, page = [], set(), 1
        while True:
            lote = self.get(url, page=page, **params)
            if isinstance(lote, dict):
                lote = lote.get("data") or lote.get("items") or lote.get("results") or []
            if not lote:
                break

            nuevos = 0
            for x in lote:
                ident = (x.get("id") or x.get("_id") or
                         x.get("docNumber") or repr(x)[:120]) if isinstance(x, dict) else repr(x)[:120]
                if ident in vistos:
                    continue
                vistos.add(ident)
                salida.append(x)
                nuevos += 1

            self._log(f"    pagina {page:>3}  +{nuevos:<4} nuevos   total {len(salida)}")
            if nuevos == 0:
                self._log("    (el endpoint ignora la paginacion, se corta aqui)")
                break
            if len(lote) < 50:
                break
            page += 1
            time.sleep(PAUSA)
            if page > 500:
                self._log("    [aviso] corte de seguridad a 500 paginas")
                break
        if etiqueta:
            self._log(f"  {etiqueta}: {len(salida)} registros")
        return salida
