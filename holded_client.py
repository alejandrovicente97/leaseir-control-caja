# -*- coding: utf-8 -*-
"""
============================================================================
 LEASEIR - Cliente de la API de Holded (v2, con respaldo a v1)
============================================================================
 Holded lanzo en junio de 2026 una API nueva y dejo la anterior obsoleta.
 Conviven dos mundos y hay que hablar el idioma que toque:

   API v2   https://api.holded.com/api/v2/...
            token pat_...          cabecera  Authorization: Bearer
            paginacion por cursor  {items, cursor, has_more}
            permisos por ambito    falta uno -> 403

   API v1   https://api.holded.com/api/invoicing/v1/...
            clave hex de 32        cabecera  key:
            paginacion por page
            OBSOLETA, "dejara de funcionar"

 De donde sale esto: el run #3 devolvio {"status":0,"info":"Invalid key"} con
 HTTP 400 en todos los endpoints v1. La causa no era el token sino que se
 estaba llamando a la API vieja con un token de la nueva.

 El cliente detecta solo cual aplica, y ademas prueba varios nombres de ruta
 por recurso: la referencia lista los endpoints por titulo, no por path, asi
 que en lugar de apostar por un nombre se prueban los candidatos y se registra
 el que responde.
============================================================================
"""
from __future__ import annotations

import time
from datetime import datetime, date, timezone

import requests

BASE_V2 = "https://api.holded.com/api/v2"
BASE_V1 = "https://api.holded.com/api/invoicing/v1"
BASE_V1_CONTA = "https://api.holded.com/api/accounting/v1"
TIMEOUT = 60
PAUSA = 0.25
LIMITE = 100


def ts(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())


class HoldedError(RuntimeError):
    pass


class Holded:

    def __init__(self, api_key: str, verboso: bool = True):
        if not api_key:
            raise HoldedError("No hay API key. Define HOLDED_API_KEY en el entorno.")
        self.key = api_key.strip()
        self.s = requests.Session()
        self.version: str | None = None      # 'v2' | 'v1'
        self.verboso = verboso
        self.bitacora: list[dict] = []
        self.rutas: dict[str, str] = {}      # recurso -> ruta que funciona
        self.truncados: dict[str, int] = {}  # url -> registros, si parece cortada

    # -----------------------------------------------------------------------
    def _log(self, t: str) -> None:
        if self.verboso:
            print(t, flush=True)

    def _cab(self, version: str) -> dict:
        h = {"Accept": "application/json", "User-Agent": "leaseir-control-caja/2.0"}
        if version == "v2":
            h["Authorization"] = f"Bearer {self.key}"
        else:
            h["key"] = self.key
        return h

    # -----------------------------------------------------------------------
    def autenticar(self) -> str:
        """Decide si la clave es de la API v2 o de la v1, probandolo."""
        if self.version:
            return self.version

        # El formato ya da una pista fuerte, pero se comprueba de verdad.
        orden = ["v2", "v1"] if self.key.startswith("pat_") else ["v1", "v2"]
        pruebas = {"v2": f"{BASE_V2}/invoices", "v1": f"{BASE_V1}/documents/invoice"}

        # Huella de la clave, nunca la clave. Distingue "faltan permisos" de
        # "el valor pegado en Secrets no es un token": si alguien copia lo que
        # se ve en pantalla en Holded, pega la version enmascarada pat_..._<XX>
        # y eso tambien acaba en un 403 que parece de permisos.
        k = self.key
        pistas = []
        if "<" in k or ">" in k:
            pistas.append("CONTIENE < o > : parece la version ENMASCARADA que "
                          "Holded muestra en pantalla, no el token real")
        if k != k.strip():
            pistas.append("tiene espacios al principio o al final")
        if " " in k or "\n" in k:
            pistas.append("tiene espacios o saltos de linea dentro")
        if not k.startswith("pat_") and len(k) != 32:
            pistas.append("ni empieza por pat_ ni tiene 32 caracteres")
        self._log(f"  Clave recibida: {len(k)} caracteres, "
                  f"prefijo {k[:4]!r}, sufijo {k[-2:]!r}")
        for p in pistas:
            self._log(f"  [ATENCION] {p}")
        if not pistas:
            self._log("  La clave tiene buena pinta por formato")

        self._log("  Detectando version de la API de Holded")
        for v in orden:
            url = pruebas[v]
            try:
                r = self.s.get(url, headers=self._cab(v),
                               params={"limit": 1}, timeout=TIMEOUT)
            except requests.RequestException as e:
                raise HoldedError(f"Sin conexion con api.holded.com: {e}")

            cuerpo = (r.text or "").strip().replace("\n", " ")[:120]
            self._log(f"    {v:3s} {url:52s} HTTP {r.status_code}  {cuerpo}")
            self.bitacora.append({"version": v, "url": url,
                                  "codigo": r.status_code, "cuerpo": cuerpo})

            if r.status_code == 200:
                try:
                    r.json()
                except ValueError:
                    self._log("        responde 200 pero no es JSON, no vale")
                    continue
                self.version = v
                self._log(f"  [OK] API {v} operativa")
                return v

            if r.status_code == 403:
                raise HoldedError(
                    f"La clave es valida pero le faltan permisos (403) en {url}.\n"
                    f"En Holded > Configuracion > Desarrolladores > Credenciales,\n"
                    f"edita el token y marca los ambitos de LECTURA de ventas,\n"
                    f"compras, contactos, tesoreria y contabilidad.\n"
                    f"Respuesta: {cuerpo}")
            time.sleep(0.2)

        detalle = "\n".join(f"    {b['version']} {b['codigo']}  {b['cuerpo']}"
                            for b in self.bitacora)
        raise HoldedError(
            "La clave no funciona ni contra la API v2 ni contra la v1.\n"
            "Si empieza por 'pat_' es de la API nueva: revisa que este activa y\n"
            "con permisos en Holded > Configuracion > Desarrolladores.\n"
            "Ojo: Holded devuelve 400 (no 401) cuando la clave no vale.\n"
            f"Intentos:\n{detalle}")

    # -----------------------------------------------------------------------
    def get(self, url: str, **params):
        v = self.autenticar()
        for intento in range(4):
            try:
                r = self.s.get(url, headers=self._cab(v), params=params, timeout=TIMEOUT)
            except requests.RequestException as e:
                self._log(f"    [aviso] red: {e}")
                time.sleep(2 ** intento)
                continue
            if r.status_code == 200:
                try:
                    return r.json()
                except ValueError:
                    return None
            if r.status_code in (429, 500, 502, 503, 504):
                espera = 2 ** intento
                self._log(f"    HTTP {r.status_code}, reintento en {espera}s")
                time.sleep(espera)
                continue
            if r.status_code == 403:
                self._log(f"    [PERMISOS] 403 en {url}: al token le falta ese ambito")
                return None
            self._log(f"    [aviso] HTTP {r.status_code} en {url} "
                      f"-> {(r.text or '')[:120].strip()}")
            return None
        return None

    # -----------------------------------------------------------------------
    def listar(self, recurso: str, candidatos: list[str], **params) -> list:
        """
        Descarga un recurso completo probando rutas candidatas hasta acertar.
        Pagina por cursor en v2 y por page en v1.
        """
        v = self.autenticar()
        base = BASE_V2 if v == "v2" else BASE_V1

        ruta = self.rutas.get(recurso)
        pendientes = [ruta] if ruta else candidatos

        for cand in pendientes:
            url = cand if cand.startswith("http") else f"{base}/{cand.lstrip('/')}"
            datos = (self._paginar_cursor(url, **params) if v == "v2"
                     else self._paginar_page(url, **params))
            if datos is not None:
                self.rutas[recurso] = cand
                self._log(f"  {recurso}: {len(datos)} registros  ({cand})")
                return datos

        self._log(f"  [aviso] {recurso}: ninguna ruta ha respondido "
                  f"({', '.join(candidatos)})")
        return []

    # -----------------------------------------------------------------------
    def _paginar_cursor(self, url: str, **params) -> list | None:
        """API v2: {items, cursor, has_more}. Devuelve None si la ruta no existe."""
        salida, cursor, vueltas = [], None, 0
        while True:
            p = dict(params); p["limit"] = LIMITE
            if cursor:
                p["cursor"] = cursor
            d = self.get(url, **p)
            if d is None:
                return salida if salida else None
            if isinstance(d, list):                    # por si devuelve lista pelada
                salida.extend(d)
                return salida
            items = d.get("items") or d.get("data") or []
            salida.extend(items)
            # el cursor no siempre se llama igual ni vive en la raiz
            meta = d.get("meta") if isinstance(d.get("meta"), dict) else {}
            cursor = (d.get("cursor") or d.get("next_cursor") or d.get("nextCursor")
                      or meta.get("cursor") or meta.get("next_cursor"))
            vueltas += 1
            if vueltas == 1 or vueltas % 10 == 0:
                self._log(f"    pagina {vueltas:>3}  total {len(salida)}")
            # La documentacion de Holded pagina con  do { ... } while (cursor).
            # No mira has_more para seguir. Se hace igual: mientras haya cursor
            # y la pagina traiga algo, se sigue. Cortar por has_more cuando aun
            # hay cursor fue lo que dejo los abonos de venta en 100 justos.
            if not cursor or not items:
                if salida and len(salida) % LIMITE == 0:
                    # Acabar en un multiplo exacto del limite sin cursor es la
                    # firma de una descarga truncada, no de un recurso agotado.
                    self._log(f"    [SOSPECHA] corta en {len(salida)} (multiplo de "
                              f"{LIMITE}) sin cursor. Claves de la respuesta: "
                              f"{sorted(d.keys()) if isinstance(d, dict) else type(d)}")
                    extra = self._rescatar(url, salida, **params)
                    if extra:
                        salida.extend(extra)
                    else:
                        self.truncados[url] = len(salida)
                break
            time.sleep(PAUSA)
            if vueltas > 400:
                self._log("    [aviso] corte de seguridad a 400 paginas")
                break
        return salida

    # -----------------------------------------------------------------------
    def _rescatar(self, url: str, ya: list, **params) -> list:
        """
        Segunda oportunidad cuando un endpoint v2 corta sin devolver cursor.

        Pasa con /credit-notes: devuelve 100 justos y ahi se queda. Y los
        abonos importan, porque restan del pendiente de cobro: quedarse con
        los primeros 100 no es perder detalle, es inflar lo que se espera
        cobrar. Antes de darlo por bueno se prueba paginar a la vieja usanza,
        por page y por offset, quedandose con lo que traiga ids nuevos.
        """
        vistos = {x.get("id") or x.get("_id") for x in ya if isinstance(x, dict)}
        for nombre in ("page", "offset"):
            rescatado, n = [], 0
            for i in range(1, 200):
                valor = i + 1 if nombre == "page" else i * LIMITE
                p = dict(params); p["limit"] = LIMITE; p[nombre] = valor
                d = self.get(url, **p)
                items = (d.get("items") or d.get("data") or []) if isinstance(d, dict) else (d or [])
                nuevos = [x for x in items if isinstance(x, dict)
                          and (x.get("id") or x.get("_id")) not in vistos]
                if not nuevos:
                    break
                for x in nuevos:
                    vistos.add(x.get("id") or x.get("_id"))
                rescatado.extend(nuevos); n += 1
                time.sleep(PAUSA)
            if rescatado:
                self._log(f"    [RESCATE] +{len(rescatado)} registros paginando "
                          f"por '{nombre}' en {n} vueltas")
                return rescatado
        self._log("    [RESCATE] ni page ni offset devuelven nada nuevo: "
                  "se da por completo en 100")
        return []

    def _paginar_page(self, url: str, **params) -> list | None:
        """API v1: paginacion por page. Corta tambien por repeticion."""
        salida, vistos, page = [], set(), 1
        while True:
            d = self.get(url, page=page, **params)
            if d is None:
                return salida if salida else None
            if isinstance(d, dict):
                d = d.get("data") or d.get("items") or []
            if not d:
                break
            nuevos = 0
            for x in d:
                ident = ((x.get("id") or x.get("_id") or repr(x)[:120])
                         if isinstance(x, dict) else repr(x)[:120])
                if ident in vistos:
                    continue
                vistos.add(ident); salida.append(x); nuevos += 1
            if nuevos == 0:
                break
            if len(d) < 50:
                break
            page += 1
            time.sleep(PAUSA)
            if page > 400:
                break
        return salida
