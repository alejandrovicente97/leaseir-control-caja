# Subir a GitHub

El repo ya está inicializado y con el primer commit hecho. Solo falta el remoto.

## 1. Crea el repositorio vacío

En github.com → New repository → nombre `leaseir-control-caja` → **Private** →
**sin** README, **sin** .gitignore, **sin** licencia (ya vienen en el commit).

## 2. Descomprime y empuja

```bash
unzip leaseir-control-caja.zip
cd leaseir
git remote add origin https://github.com/<TU_USUARIO>/leaseir-control-caja.git
git branch -M main
git push -u origin main
```

Si prefieres no descomprimir, el `.bundle` lleva el historial completo:

```bash
git clone leaseir-control-caja.bundle leaseir
cd leaseir
git remote set-url origin https://github.com/<TU_USUARIO>/leaseir-control-caja.git
git push -u origin main
```

## Antes de nada

Revoca la API key de Holded que me pasaste por el chat y genera otra:
Holded → Ajustes → Desarrolladores → Credenciales. La nueva va en una variable
de entorno (`HOLDED_API_KEY`), nunca en el repo.
