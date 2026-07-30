# Puesta en marcha — de los Excel a la API, sin tocar nada cada día

Objetivo: que cada mañana a las 07:30 el forecast se calcule solo, con datos
recién sacados de Holded y del calendario de Eli, sin que tu portátil tenga que
estar encendido.

Son cuatro pasos y se hacen una sola vez. Cuenta 25 minutos.

---

## Por qué GitHub Actions y no tu PC

La llamada a `api.holded.com` tiene que salir de una máquina con internet. Se
comprobó que no sirven:

- el entorno donde corre el motor (Anthropic filtra la salida por lista blanca);
- el puente a tu máquina (`api.holded.com`, `api.github.com` y `google.com`
  fallan los tres desde ahí).

GitHub Actions sí tiene salida libre, es gratis en repos privados hasta 2.000
minutos al mes (este trabajo gasta unos 2 minutos al día, ~40 al mes), guarda
las credenciales cifradas y corre aunque tú estés de vacaciones.

---

## Paso 1 · Crear el repositorio y subir el código

En github.com → **New repository**

- Nombre: `leaseir-control-caja`
- **Private**
- Sin README, sin .gitignore, sin licencia

Luego, en tu terminal:

```bash
unzip leaseir-control-caja.zip
cd leaseir
git remote add origin https://github.com/TU_USUARIO/leaseir-control-caja.git
git branch -M main
git push -u origin main
```

---

## Paso 2 · La API key de Holded, en Secrets

**Antes de nada: revoca el token que pasaste por el chat.**
Holded → Ajustes → Desarrolladores → Credenciales → borra el viejo → **Añadir
token API** con permisos de LECTURA sobre Facturación, Contactos, Tesorería y
Contabilidad.

En el repo: **Settings → Secrets and variables → Actions → New repository secret**

| Name | Secret |
|---|---|
| `HOLDED_API_KEY` | el token nuevo, tal cual, sin comillas |

---

## Paso 3 · Cuenta de servicio de Google para el fichero de Eli

Una cuenta de servicio es un "usuario robot" que puede leer el Sheet de
madrugada sin que nadie inicie sesión.

**3.1 · Crearla**

1. [console.cloud.google.com](https://console.cloud.google.com) → crea un proyecto
   (por ejemplo `leaseir-finanzas`).
2. **APIs y servicios → Biblioteca** → busca **Google Drive API** → *Habilitar*.
3. **APIs y servicios → Credenciales → Crear credenciales → Cuenta de servicio**.
   Nombre: `motor-caja`. Sin roles: no los necesita.
4. Entra en la cuenta creada → pestaña **Claves** → **Agregar clave → Crear
   clave nueva → JSON**. Se descarga un fichero.

**3.2 · Darle acceso al fichero de Eli**

Abre el JSON y copia el valor de `client_email` (algo como
`motor-caja@leaseir-finanzas.iam.gserviceaccount.com`).

Abre el [Sheet de Eli](https://docs.google.com/spreadsheets/d/1EmO9WHz-ewB8objYRnAvoQ2ZBkhnzAbR)
→ **Compartir** → pega ese email → permiso **Lector** → quita la notificación
por correo → Enviar.

**3.3 · Guardarla en Secrets**

Nuevo secret en el repo:

| Name | Secret |
|---|---|
| `GOOGLE_SERVICE_ACCOUNT_JSON` | el **contenido completo** del JSON, pegado tal cual |

Para comprobar que funciona antes de nada, en tu máquina:

```bash
export GOOGLE_SERVICE_ACCOUNT_JSON="$(cat ~/Descargas/leaseir-finanzas-xxxx.json)"
python google_sheets.py
```

Debe imprimir el número de cuotas y de facturas del calendario.

---

## Paso 4 · Activar GitHub Pages

**Settings → Pages → Source: GitHub Actions**

> **Aviso importante sobre privacidad.** En los planes Free, Pro y Team, un sitio
> de Pages es **público aunque el repositorio sea privado**: cualquiera con la URL
> ve el dashboard. El control de acceso a Pages solo existe en **GitHub Enterprise
> Cloud**.
>
> Con datos de tesorería eso no es aceptable. Dos salidas:
>
> - **Si tenéis Enterprise Cloud:** Settings → Pages → *Private* y listo.
> - **Si no:** deja Pages desactivado. El workflow ya guarda el dashboard como
>   **artefacto privado** de la ejecución (Actions → última ejecución → Artifacts,
>   90 días de retención) y lo commitea en `publicado/index.html`, ambos visibles
>   solo para quien tenga acceso al repo. Es igual de cómodo y de verdad privado.
>
> Para desactivar Pages, borra del workflow el paso *Subir a GitHub Pages* y el
> job *publicar*.

---

## Comprobar que todo va

**Actions → Control de caja Leaseir → Run workflow** (lánzalo a mano la primera vez).

Deberías ver los cinco pasos en verde y, al final, el artefacto descargable.

Si algo falla:

| Síntoma | Causa casi segura |
|---|---|
| `Falta el secret HOLDED_API_KEY` | No lo guardaste, o hay un espacio delante |
| `La API key no es valida (HTTP 401)` | Token revocado o sin permisos de lectura |
| `Drive devuelve 404` | No compartiste el Sheet con el `client_email` |
| El forecast sale a cero | El calendario bajó vacío: revisa que la pestaña siga llamándose `ELISABET` |

En el paso *Extraer Holded* el log enseña cuántos registros trae cada bloque.
Si algún campo no encaja, ejecuta en tu máquina `python holded_extract.py --probar`
y pégame la salida: enseña los nombres reales que devuelve la API y ajusto el
mapeo en cinco minutos.

---

## Traerlo a OneDrive

`4_SINCRONIZAR_ONEDRIVE.bat` hace `git pull` y copia el dashboard a
`19. Control Caja\_motor_caja\`. Ejecútalo cuando quieras, o prográmalo a las
08:00 con el mismo `schtasks` que los otros.

---

## El día a día

Ninguno. El Action corre solo. Lo único que se toca es `config.yaml` cuando
cambie un criterio de negocio:

| Cuándo | Qué tocar |
|---|---|
| Sube la nómina o cambia la plantilla | `salarios` |
| Se firma o se cancela un S&L | `cuotas_sl.operaciones` |
| Aparece un gasto recurrente nuevo | `recurrentes.proveedores` |
| Cierras una venta que aún no facturas | `cobros.sin_facturar` |
| Tienes criterio sobre un cobro concreto | `cobros.ajustes_positivos` |
| Un cliente entra en concurso | `cobros.excluir_clientes` |

Cambias el fichero, `git push`, y el forecast del día siguiente ya lo recoge.
