#!/bin/bash
# Script de configuración inicial del Sistema Consolidado de Trading
# =================================================================

set -e

echo "🚀 Configurando Sistema Consolidado de Trading..."

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Función para log
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING: $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}"
}

# Verificar Python
log "Verificando Python..."
if ! command -v python3 &> /dev/null; then
    error "Python3 no está instalado"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
log "Python version: $PYTHON_VERSION"

# Verificar pip
if ! command -v pip3 &> /dev/null; then
    error "pip3 no está instalado"
    exit 1
fi

# Crear entorno virtual
log "Creando entorno virtual..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    log "Entorno virtual creado"
else
    warn "Entorno virtual ya existe"
fi

# Activar entorno virtual
log "Activando entorno virtual..."
source venv/bin/activate

# Actualizar pip
log "Actualizando pip..."
pip install --upgrade pip

# Instalar dependencias
log "Instalando dependencias..."
pip install -r requirements.txt

# Crear archivo .env si no existe
if [ ! -f ".env" ]; then
    log "Creando archivo .env..."
    cp .env.example .env
    warn "IMPORTANTE: Edita el archivo .env con tus configuraciones"
else
    warn "Archivo .env ya existe"
fi

# Crear directorios necesarios
log "Creando directorios..."
mkdir -p data/{raw,processed,models,backtest}
mkdir -p logs
mkdir -p notebooks

# Verificar Docker
log "Verificando Docker..."
if command -v docker &> /dev/null; then
    log "Docker está disponible"
    
    if command -v docker-compose &> /dev/null; then
        log "Docker Compose está disponible"
    else
        warn "Docker Compose no está disponible"
    fi
else
    warn "Docker no está disponible - algunas funciones pueden no funcionar"
fi

# Configurar pre-commit hooks
log "Configurando pre-commit hooks..."
if command -v pre-commit &> /dev/null; then
    pre-commit install
    log "Pre-commit hooks configurados"
else
    warn "pre-commit no está instalado - saltando hooks"
fi

# Verificar configuración
log "Verificando configuración..."
python3 -c "
import yaml
try:
    with open('config/settings.yaml', 'r') as f:
        config = yaml.safe_load(f)
    print('✅ Configuración válida')
except Exception as e:
    print(f'❌ Error en configuración: {e}')
    exit(1)
"

# Ejecutar tests básicos
log "Ejecutando tests básicos..."
if [ -d "tests" ]; then
    python3 -m pytest tests/ -v --tb=short || warn "Algunos tests fallaron"
else
    warn "No se encontraron tests"
fi

log "✅ Configuración completada!"
echo ""
echo "📋 Próximos pasos:"
echo "1. Editar el archivo .env con tus API keys"
echo "2. Ejecutar: source venv/bin/activate"
echo "3. Ejecutar: python -m src.main"
echo ""
echo "🐳 Para usar Docker:"
echo "1. docker-compose up -d"
echo ""
echo "📊 Accesos:"
echo "- API: http://localhost:8000"
echo "- Dashboard: http://localhost:3000"
echo "- Grafana: http://localhost:3001"
echo "- Jupyter: http://localhost:8888"
echo ""
echo "📚 Documentación: docs/"