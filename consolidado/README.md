# Sistema Consolidado de Trading con RL/ML y Alertas

## Descripción
Sistema unificado que integra múltiples estrategias de Machine Learning y Reinforcement Learning para trading automatizado con sistema avanzado de alertas.

## Arquitectura del Sistema

### 📁 Estructura de Directorios

```
consolidado/
├── README.md                    # Este archivo
├── requirements.txt             # Dependencias Python
├── docker-compose.yml          # Configuración Docker
├── config/                     # Configuraciones
│   ├── settings.yaml           # Configuración principal
│   ├── exchanges.yaml          # Configuración de exchanges
│   ├── strategies.yaml         # Configuración de estrategias
│   └── alerts.yaml            # Configuración de alertas
├── src/                       # Código fuente principal
│   ├── __init__.py
│   ├── main.py               # Punto de entrada principal
│   ├── data/                 # Capa de datos
│   ├── strategies/           # Estrategias de trading
│   ├── alerts/              # Sistema de alertas
│   ├── risk/                # Gestión de riesgo
│   ├── api/                 # APIs y endpoints
│   ├── utils/               # Utilidades
│   └── web/                 # Dashboard web
├── data/                     # Almacenamiento de datos
│   ├── raw/                 # Datos crudos
│   ├── processed/           # Datos procesados
│   ├── models/              # Modelos entrenados
│   └── backtest/            # Resultados de backtesting
├── tests/                    # Tests unitarios
├── docs/                     # Documentación
├── scripts/                  # Scripts de utilidad
├── logs/                     # Archivos de log
└── deployment/               # Archivos de despliegue
    ├── kubernetes/
    └── docker/
```

## Componentes Principales

### 1. **Data Layer** - Gestión de Datos
### 2. **Strategy Layer** - Estrategias de Trading  
### 3. **Alert System** - Sistema de Alertas
### 4. **Risk Management** - Gestión de Riesgo
### 5. **API Layer** - APIs y Conectores
### 6. **Web Dashboard** - Interfaz de Usuario

## Tecnologías Utilizadas

- **Backend**: Python 3.9+, FastAPI, Celery
- **ML/RL**: PyTorch, TensorFlow, Stable-Baselines3, FinRL
- **Data**: PostgreSQL, Redis, InfluxDB, Apache Kafka
- **Monitoring**: Prometheus, Grafana, ELK Stack
- **Deployment**: Docker, Kubernetes
- **Frontend**: React, TypeScript, Chart.js

## Instalación Rápida

```bash
# Clonar y navegar al directorio
cd consolidado

# Instalar dependencias
pip install -r requirements.txt

# Configurar variables de entorno
cp .env.example .env

# Levantar servicios con Docker
docker-compose up -d

# Ejecutar sistema
python src/main.py
```

## Características Principales

- ✅ **Multi-Exchange**: Binance, Alpaca, Kraken, etc.
- ✅ **Multi-Strategy**: RL, ML, Technical Analysis
- ✅ **Real-time Alerts**: Email, SMS, Telegram, Discord
- ✅ **Risk Management**: Stop-loss, Position sizing
- ✅ **Backtesting**: Validación histórica de estrategias
- ✅ **Web Dashboard**: Monitoreo en tiempo real
- ✅ **API REST**: Integración externa
- ✅ **Escalable**: Arquitectura microservicios

## Próximos Pasos

1. Configurar exchanges y APIs
2. Definir estrategias de trading
3. Configurar alertas personalizadas
4. Ejecutar backtesting
5. Desplegar en producción