# Leaseir · Control de caja y forecast

Motor de tesorería que sustituye al forecast de Holded y al Excel
`Forecast CashFlow.xlsx`. Cruza las facturas de Holded con el calendario de
cobros de Eli, proyecta lo que no existe como factura (salarios, cuotas de banco,
rentings, gastos recurrentes) y publica un dashboard HTML.

---

## Por qué existe

El forecast de Holded falla por tres motivos, y los tres se corrigen aquí:

| Problema | Qué hace este motor |
|---|---|
| Holded da el saldo vivo de la factura como si fuera exigible hoy | Usa el **calendario de cuotas de Eli**: exigible = cuota teórica acumulada − cobrado real |
| Holded no conoce nóminas, cuotas S&L ni gastos recurrentes | Los proyecta desde `config.yaml` y desde el histórico, **solo en los meses sin factura** |
| Holded no sabe que un renting se facturará dentro de dos meses | Proyecta las cuotas del calendario que aún no tienen factura emitida |

Y añade el control que un controller necesita:
**cobros − pagos del mes = saldo final − saldo inicial**.

---

## Arquitectura

```
  TU PC (con internet)                    ESTE MOTOR
  ─────────────────────                   ──────────────────────────────
  holded_extract.py  ──►  holded.json  ──►  fuentes.py   normaliza
   (API de Holded)         en OneDrive       motor.py     calcula
                                             dashboard.py pinta
  Sheet de Eli (Drive) ─────────────────►    run.py       orquesta
                                                │
                                                ▼
                                        caja_leaseir.html
```

El extractor corre en tu máquina porque el entorno donde vive el motor tiene la
salida a `api.holded.com` bloqueada por lista blanca. Todo lo demás es automático.

---

## Puesta en marcha

### 1. Extraer Holded (en tu PC, una vez al día)

```bat
pip install requests
set HOLDED_API_KEY=tu_token_de_holded
python holded_extract.py
```

Deja `holded.json` en `19. Control Caja\_data_holded\`. Para automatizarlo,
programa esa línea en el Programador de tareas de Windows a las 7:30.

Trae: facturas de venta y compra, abonos, contactos, cuentas de tesorería,
**movimientos bancarios** (los que permiten el cuadre) y libro diario.

### 2. Generar el dashboard

```bash
pip install pandas openpyxl pyyaml
python run.py                     # usa Holded si encuentra el json, si no los Excel
python run.py --fuente excel      # fuerza los Excel de la carpeta
python run.py --mes 202608        # fija el mes en curso
```

---

## `config.yaml` — todo el criterio de negocio

Nada de esto está en el código. Se toca aquí:

| Bloque | Qué controla |
|---|---|
| `salarios` | Nómina neta, SS y servicios con IVA. Hoy: 266.070 €/mes |
| `cuotas_sl` | Las 14 cuotas de S&L con Santander, BBVA, Sabadell y CSI. Hoy: 133.928 €/mes |
| `recurrentes` | Nobis, Miraloma, Maria Martire, transporte, suministros, software, renting de vehículos |
| `cobros.sin_facturar` | Ventas comprometidas sin factura (Elha) |
| `cobros.ajustes_positivos` | **Tu criterio comercial.** Lo que en el Excel metías a mano |
| `cobros.excluir_clientes` | Intercompañía e incobrables. Se calculan igual, pero fuera del forecast |
| `cobros.rentings_financiados` | Rentings cedidos al banco: entran íntegros con desfase de 2 meses |
| `cuadre.tolerancia_eur` | Umbral del check de caja |

---

## Reglas del motor

**Cobros.** `exigible = cuota teórica acumulada del calendario − cobrado real`.
De un renting a 36 meses solo es caja de este mes la parte de cuotas vencidas.
El alcance arranca en el primer mes del calendario (enero 2025): antes de ahí no
hay cuotas cargadas y saldrían anticipos falsos de millones.

**Pagos.** El forecast del mes X recoge todo lo pendiente con vencimiento ≤ fin de
X, así los vencidos se arrastran al mes en curso en vez de perderse.

**Recurrentes.** Si el proveedor ya tiene factura en Holded con vencimiento en ese
mes, se usa la factura. Si no, se proyecta la mediana de los meses con gasto de los
últimos 12. Nunca se duplica.

**Cuadre.** `cobros − pagos` contra la variación de saldo. Lo que no cuadre son
movimientos que no pasan por factura: nóminas, impuestos, comisiones, pólizas,
préstamos y traspasos entre cuentas propias.

---

## Hallazgos sobre el Excel actual

Detectados al reproducir la lógica:

1. **Las cuatro columnas de meses futuros del `Cuadro de Control` apuntan todas a
   `$J$1`.** Las mismas facturas de renting de junio (241.662 €) se cuentan en
   agosto, septiembre, octubre y noviembre. Aquí cada factura cae solo en su mes.
2. **`$J$1` estaba en 202606** con el fichero cerrado a 17/07/2026.
3. **99 filas del `Cuadro de Control` apuntan a facturas que no están en la pestaña
   Holded** (fórmulas arrastradas por delante de los datos): devuelven `#N/A` y sus
   cobros no entran en el forecast.
4. **35 abonos faltan en el `Cuadro de Control`** (1,12 M €): los cobros salen
   sobrevalorados.
5. **Leaseir Medical Light, S.L.: 13 facturas por 1.186.152 € con cobro cero.**
   Es intercompañía y no se cobra — excluida en `config.yaml`.

---

## Ficheros

| Fichero | Qué hace |
|---|---|
| `holded_extract.py` | Cliente de la API de Holded. Corre en tu PC |
| `fuentes.py` | Normaliza Holded / Excel / calendario de Eli a un esquema único |
| `motor.py` | Forecast, certidumbre 1-6, cuadre y alertas |
| `dashboard.py` | HTML autocontenido. Paleta validada para daltonismo |
| `run.py` | Orquestador |
| `config.yaml` | Todo el criterio de negocio |

---

## Seguridad

La API key de Holded **nunca** se commitea: va por variable de entorno y `.env`
está en `.gitignore`. Si se ha expuesto alguna vez, revócala en
Holded → Ajustes → Desarrolladores → Credenciales y genera otra.
