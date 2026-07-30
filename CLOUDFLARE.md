# El link del dashboard, con puerta de login

Objetivo: una URL que abras desde el móvil o desde el portátil y muestre el
control de caja del día — pero que solo puedan abrir las personas de Leaseir que
tú autorices.

**Por qué no GitHub Pages.** En el plan actual, GitHub responde literalmente
*"Upgrade or make this repository public to enable Pages"*. Y aunque se pague
Pro o Team, el sitio publicado **sigue siendo público aunque el repositorio sea
privado**: las Pages con control de acceso solo existen en GitHub Enterprise.
Publicar ahí la posición de caja, las nóminas y las cuotas bancarias en una URL
adivinable (`alejandrovicente97.github.io/leaseir-control-caja/`) no es asumible.

Cloudflare hace las dos cosas gratis: aloja el sitio y le pone delante un login.

Cuenta 15 minutos.

---

## Paso 1 · Cuenta de Cloudflare y proyecto de Pages

1. Regístrate en [dash.cloudflare.com](https://dash.cloudflare.com) (plan Free).
2. Menú lateral → **Workers & Pages** → **Create** → pestaña **Pages** →
   **Create using direct upload**.
3. Nombre del proyecto: **`caja-leaseir`** (tiene que coincidir exactamente con
   el `--project-name` del workflow).
4. Crea el proyecto. Todavía no subas nada: lo hará el Action.

La URL será **`https://caja-leaseir.pages.dev`**.

---

## Paso 2 · Credenciales para que el Action despliegue

**Account ID:** en Workers & Pages, panel derecho, *Account ID*. Cópialo.

**API token:** icono de perfil → **My Profile** → **API Tokens** →
**Create Token** → plantilla **Edit Cloudflare Workers**, o token
personalizado con el permiso `Account · Cloudflare Pages · Edit`.

En el repo → **Settings → Secrets and variables → Actions**:

| Name | Valor |
|---|---|
| `CLOUDFLARE_API_TOKEN` | el token creado |
| `CLOUDFLARE_ACCOUNT_ID` | el Account ID |

> Si no pones estos dos secrets no pasa nada: el workflow lo detecta, avisa y
> sigue adelante dejando el dashboard como artefacto y en `publicado/`.

---

## Paso 3 · La puerta de login (esto es lo importante)

Sin este paso, `caja-leaseir.pages.dev` sería **público**. No te saltes el paso 3.

1. En Cloudflare → **Zero Trust** (menú lateral). La primera vez pide elegir un
   nombre de equipo y un plan: elige **Free** (hasta 50 usuarios).
2. **Access → Applications → Add an application → Self-hosted**.
3. Configura:
   - *Application name*: `Caja Leaseir`
   - *Session duration*: 24 horas
   - *Public hostname*: subdominio `caja-leaseir`, dominio `pages.dev`
4. **Add policy**:
   - *Policy name*: `Finanzas Leaseir`
   - *Action*: **Allow**
   - *Include* → **Emails ending in** → `@leaseir.com`

   Si quieres afinar más, usa *Include → Emails* y lista los correos concretos
   (el tuyo, el de Nacho, el de Eli).
5. Guarda.

A partir de ahí, quien abra la URL recibe un código de un solo uso en su correo
corporativo. Sin correo autorizado, no entra.

---

## Comprobar

Lanza el workflow: **Actions → Control de caja Leaseir → Run workflow**.

En el log, el paso *Publicar en Cloudflare Pages* deja la URL del despliegue.
Abre `https://caja-leaseir.pages.dev` en una ventana de incógnito: debe pedirte
el correo. Ese es el comportamiento correcto — si entra directo, la política de
Access no está aplicada y hay que revisar el paso 3.

---

## Dominio propio (opcional)

Si prefieres `caja.leaseir.com`: en el proyecto de Pages →
**Custom domains → Set up a domain**. Requiere que `leaseir.com` esté gestionado
en Cloudflare o añadir el CNAME que te indique. Después, en la aplicación de
Access, cambia el hostname al nuevo dominio.

---

## Resumen de secrets

| Secret | Para qué | Sin él |
|---|---|---|
| `HOLDED_API_KEY` | Extraer facturas y tesorería | El workflow falla |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Leer el calendario de Eli | El workflow falla |
| `CLOUDFLARE_API_TOKEN` | Publicar el dashboard | Avisa y sigue; solo artefacto |
| `CLOUDFLARE_ACCOUNT_ID` | Publicar el dashboard | Igual |
