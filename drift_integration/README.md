# 🚀 Drift Trading Bot - DRL Integration

## 📋 Descripción

Bot de trading de Deep Reinforcement Learning integrado con **Drift Protocol** en Solana, optimizado para generar retornos del **900%** anual a través de:

- **Arquitectura AggressiveDQN** con Dueling Networks y Noisy Networks
- **Trading en tiempo real** con Drift Protocol
- **32 características avanzadas** incluyendo indicadores técnicos, funding rates, y microestructura de mercado
- **Gestión de riesgo inteligente** con stop-loss dinámicos
- **Múltiples activos** (SOL-PERP, BTC-PERP, ETH-PERP, BONK-PERP)

## 🎯 Objetivos de Performance

- **Retorno anual objetivo:** 900%
- **Retorno mensual objetivo:** 150%
- **Retorno diario objetivo:** 5%
- **Sharpe Ratio mínimo:** 2.0
- **Máximo drawdown:** 15%

## 🛠️ Características Técnicas

### **Arquitectura del Modelo**
- **Dueling Double DQN** con Noisy Networks
- **Prioritized Experience Replay**
- **Multi-step Learning** (n=3)
- **Attention Mechanism** para importancia de características
- **Market Regime Classification** (tarea auxiliar)

### **Características de Trading**
- **32 features** en tiempo real:
  - 8 features de precio (momentum, volatilidad, spreads)
  - 4 features de volumen y liquidez
  - 4 features de funding rates
  - 8 features de posición y cuenta
  - 8 indicadores técnicos (RSI, MACD, Bollinger, EMAs)

### **Gestión de Riesgo**
- Stop-loss dinámicos por activo
- Límites de pérdida diaria (5%)
- Emergency stop en 25% de pérdida
- Máximo 3 pérdidas consecutivas
- Leverage dinámico (2-10x)

## 📦 Instalación

### **1. Requisitos del Sistema**
```bash
Python 3.8+
CUDA (recomendado para GPU)
Node.js (para algunas dependencias de Solana)
```

### **2. Instalación Automática**
```bash
cd drift_integration
python setup_and_test.py
```

### **3. Instalación Manual**
```bash
# Instalar dependencias
pip install -r requirements_drift.txt

# Configurar variables de entorno
cp .env.example .env
# Editar .env con tu private key
```

## ⚙️ Configuración

### **1. Wallet de Solana**
```bash
# Generar wallet para devnet
solana-keygen new --outfile ~/.config/solana/devnet.json

# Obtener devnet SOL
solana airdrop 2 --url devnet

# Obtener tu private key (Base58)
solana-keygen pubkey ~/.config/solana/devnet.json
```

### **2. Variables de Entorno (.env)**
```bash
SOLANA_PRIVATE_KEY="tu_private_key_base58"
SOLANA_PUBLIC_KEY="tu_public_key"
DRIFT_ENVIRONMENT="devnet"  # o "mainnet"
INITIAL_CAPITAL=1000.0
```

### **3. Configuración de Trading (config/drift_config.yaml)**
```yaml
trading:
  preferred_assets:
    - name: "SOL-PERP"
      market_index: 0
      max_leverage: 5
      position_size_pct: 0.5
      stop_loss_pct: 0.15
      take_profit_pct: 0.25
```

## 🚀 Uso

### **1. Entrenamiento**
```bash
# Entrenamiento en devnet
python src/drift_trainer.py train

# Con parámetros personalizados
python src/drift_trainer.py train --episodes 1000 --eval-freq 50
```

### **2. Backtesting**
```bash
# Backtest histórico
python src/drift_trainer.py backtest

# Backtesting con fechas específicas
python src/drift_trainer.py backtest --start 2024-01-01 --end 2024-12-31
```

### **3. Trading en Vivo (⚠️ RIESGO REAL)**
```bash
# SOLO DESPUÉS DE BACKTESTING EXITOSO
python src/drift_trainer.py live
```

### **4. Evaluación**
```bash
# Evaluar modelo entrenado
python src/drift_trainer.py eval
```

### **5. Monitoreo**
```bash
# Ver métricas en tiempo real
python src/monitor.py --port 8000
# Abrir http://localhost:8000
```

## 📊 Activos Recomendados

### **Para Principiantes (Bajo Riesgo)**
```yaml
SOL-PERP:
  - Volatilidad: 5-15% diaria
  - Liquidez: Excelente
  - Leverage recomendado: 2-5x
  
BTC-PERP:
  - Volatilidad: 3-8% diaria
  - Liquidez: Máxima
  - Leverage recomendado: 2-3x
```

### **Para Expertos (Alto Riesgo/Recompensa)**
```yaml
BONK-PERP:
  - Volatilidad: 20-50% diaria
  - Potencial de +900%: ✅
  - Leverage recomendado: 5-10x
  
ETH-PERP:
  - Volatilidad: 4-10% diaria
  - Correlación DeFi: Alta
  - Leverage recomendado: 3-5x
```

## 🎯 Estrategias para 900% Returns

### **1. Configuración Agresiva**
```yaml
model:
  learning_rate: 0.0001
  reward_type: "aggressive_profit"
  
trading:
  max_leverage: 10
  position_size_pct: 0.8  # 80% del capital
  compound_profits: true
```

### **2. Multi-Asset Portfolio**
```python
# Distribución dinámica
SOL-PERP: 40%    # Base estable
BONK-PERP: 40%   # Alto potencial
BTC-PERP: 20%    # Cobertura
```

### **3. Timing Perfecto**
- **Funding Arbitrage:** Aprovechar tasas altas
- **Breakout Momentum:** Entrar en rupturas con volumen
- **Mean Reversion:** Reversiones en alta volatilidad

## 📈 Métricas de Performance

### **Dashboard en Tiempo Real**
```bash
📊 Equity: $1,234.56 (+23.4%)
📈 Daily PnL: +$45.67 (+4.2%)
🎯 Sharpe Ratio: 2.8
📉 Max Drawdown: -8.2%
🔄 Trades Today: 15 (80% win rate)
⚡ Current Position: LONG SOL-PERP 0.5 SOL
```

### **Alertas Automáticas**
- Discord/Telegram para trades importantes
- Email para emergencias
- SMS para stop-loss triggers

## ⚠️ Gestión de Riesgo

### **Límites Automáticos**
```yaml
risk_management:
  max_daily_loss_pct: 0.05        # 5% máximo diario
  emergency_stop_loss_pct: 0.25   # 25% emergency stop
  max_consecutive_losses: 3       # Parar tras 3 pérdidas
  min_account_balance: 10.0       # Mínimo 10 USDC
```

### **Monitoreo 24/7**
- Health checks cada minuto
- Auto-restart en fallos
- Backup automático de estado

## 🔧 Troubleshooting

### **Problemas Comunes**

**❌ Error de conexión a Drift**
```bash
# Verificar RPC endpoint
curl -X POST -H "Content-Type: application/json" -d '{"jsonrpc":"2.0","id":1,"method":"getHealth"}' https://api.devnet.solana.com

# Verificar balance de SOL
solana balance --url devnet
```

**❌ Private key inválida**
```bash
# Verificar formato Base58
python -c "from solders.keypair import Keypair; print(Keypair.from_base58_string('tu_key'))"
```

**❌ Memoria insuficiente**
```bash
# Reducir batch size en config
model:
  batch_size: 64  # Reducir de 128
  memory_size: 50000  # Reducir de 100000
```

### **Logs de Debug**
```bash
# Ver logs detallados
tail -f logs/drift_training.log

# Métricas de sistema
python src/system_monitor.py
```

## 📁 Estructura del Proyecto

```
drift_integration/
├── src/
│   ├── drift_connector.py      # Conexión a Drift Protocol
│   ├── drift_environment.py    # Environment DRL
│   ├── aggressive_agent.py     # Agente DQN agresivo
│   ├── drift_trainer.py        # Script principal de entrenamiento
│   └── monitor.py              # Dashboard de monitoreo
├── config/
│   ├── drift_config.yaml       # Configuración principal
│   └── assets/                 # Configs por activo
├── checkpoints/                # Modelos guardados
├── logs/                       # Logs de trading
├── data/                       # Datos históricos
└── models/                     # Modelos entrenados
```

## 🔮 Próximas Características

- [ ] **Auto-hyperparameter tuning** con Optuna
- [ ] **Ensemble de agentes** para diferentes mercados
- [ ] **Social sentiment analysis** integration
- [ ] **Cross-chain arbitrage** (Solana ↔ Ethereum)
- [ ] **NFT trading integration**
- [ ] **Mobile app** para monitoreo

## 📞 Soporte

Para soporte y preguntas:
- **GitHub Issues:** Para bugs y mejoras
- **Discord:** Para discusiones de la comunidad
- **Telegram:** Para alertas en tiempo real

## ⚖️ Disclaimer

**⚠️ AVISO IMPORTANTE:**
- Este bot es experimental y de alto riesgo
- Nunca inviertas más de lo que puedes permitirte perder
- Los retornos pasados no garantizan resultados futuros
- El trading de criptomonedas es altamente volátil
- Usa siempre stops-loss y gestión de riesgo apropiada

## 📄 Licencia

MIT License - Ver `LICENSE` para más detalles.

---

**🚀 ¡Feliz Trading! Que las ganancias estén contigo.**