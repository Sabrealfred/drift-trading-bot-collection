"""
Sistema Consolidado de Trading - Punto de entrada principal
Integra RL, ML, alertas y gestión de riesgo
"""

import asyncio
import logging
import signal
import sys
from datetime import datetime
from typing import Dict, Any

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import load_config
from .data import DataManager
from .strategies import StrategyManager
from .alerts import AlertManager
from .risk import RiskManager
from .api import create_api_router
from .utils.logger import setup_logging
from .utils.health import HealthChecker

# Configurar logging
logger = logging.getLogger(__name__)

class TradingSystem:
    """
    Sistema principal de trading que coordina todos los componentes
    """
    
    def __init__(self, config_path: str = "config/settings.yaml"):
        self.config = load_config(config_path)
        self.running = False
        
        # Componentes principales
        self.data_manager: DataManager = None
        self.strategy_manager: StrategyManager = None
        self.alert_manager: AlertManager = None
        self.risk_manager: RiskManager = None
        self.health_checker: HealthChecker = None
        
        # FastAPI app
        self.app: FastAPI = None
        
        # Tasks en ejecución
        self.background_tasks = []
        
    async def initialize(self):
        """Inicializa todos los componentes del sistema"""
        logger.info("Inicializando Sistema Consolidado de Trading...")
        
        try:
            # Configurar logging
            setup_logging(self.config.get('monitoring', {}).get('logging', {}))
            
            # Inicializar componentes
            self.data_manager = DataManager(self.config.get('data_sources', {}))
            self.strategy_manager = StrategyManager(self.config.get('strategies', {}))
            self.alert_manager = AlertManager(self.config.get('alerts', {}))
            self.risk_manager = RiskManager(self.config.get('risk_management', {}))
            self.health_checker = HealthChecker(self.config.get('monitoring', {}))
            
            # Inicializar sistemas asíncronos
            await self.alert_manager.start()
            
            # Crear FastAPI app
            self._create_app()
            
            logger.info("Sistema inicializado exitosamente")
            
        except Exception as e:
            logger.error(f"Error inicializando sistema: {e}")
            raise
    
    def _create_app(self):
        """Crea la aplicación FastAPI"""
        self.app = FastAPI(
            title="Sistema Consolidado de Trading",
            description="Sistema unificado de trading con RL/ML y alertas",
            version="1.0.0"
        )
        
        # Configurar CORS
        cors_config = self.config.get('api', {}).get('cors', {})
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_config.get('allow_origins', ["*"]),
            allow_credentials=True,
            allow_methods=cors_config.get('allow_methods', ["*"]),
            allow_headers=["*"],
        )
        
        # Crear router de API
        api_router = create_api_router(
            self.data_manager,
            self.strategy_manager,
            self.alert_manager,
            self.risk_manager,
            self.health_checker
        )
        
        self.app.include_router(api_router, prefix="/api/v1")
        
        # Endpoints de salud
        @self.app.get("/health")
        async def health_check():
            return await self.health_checker.get_health_status()
        
        @self.app.get("/")
        async def root():
            return {
                "message": "Sistema Consolidado de Trading",
                "version": "1.0.0",
                "status": "running",
                "timestamp": datetime.now().isoformat()
            }
    
    async def start(self):
        """Inicia el sistema de trading"""
        if self.running:
            logger.warning("Sistema ya está ejecutándose")
            return
        
        self.running = True
        logger.info("Iniciando sistema de trading...")
        
        try:
            # Inicializar si no se ha hecho
            if not self.data_manager:
                await self.initialize()
            
            # Iniciar feeds de datos en tiempo real
            symbols = self.config.get('symbols', {})
            crypto_symbols = symbols.get('crypto', [])
            stock_symbols = symbols.get('stocks', [])
            all_symbols = crypto_symbols + stock_symbols
            
            if all_symbols:
                await self.data_manager.start_realtime_feeds(all_symbols)
            
            # Iniciar tareas de background
            await self._start_background_tasks()
            
            logger.info("Sistema de trading iniciado exitosamente")
            
        except Exception as e:
            logger.error(f"Error iniciando sistema: {e}")
            self.running = False
            raise
    
    async def _start_background_tasks(self):
        """Inicia tareas de background"""
        
        # Tarea de monitoreo del mercado
        market_monitor_task = asyncio.create_task(
            self._market_monitor_loop()
        )
        self.background_tasks.append(market_monitor_task)
        
        # Tarea de evaluación de estrategias
        strategy_eval_task = asyncio.create_task(
            self._strategy_evaluation_loop()
        )
        self.background_tasks.append(strategy_eval_task)
        
        # Tarea de verificación de triggers de alertas
        alert_trigger_task = asyncio.create_task(
            self._alert_trigger_loop()
        )
        self.background_tasks.append(alert_trigger_task)
        
        # Tarea de health check
        health_check_task = asyncio.create_task(
            self._health_check_loop()
        )
        self.background_tasks.append(health_check_task)
        
        logger.info(f"Iniciadas {len(self.background_tasks)} tareas de background")
    
    async def _market_monitor_loop(self):
        """Loop principal de monitoreo del mercado"""
        logger.info("Iniciado monitoreo del mercado")
        
        while self.running:
            try:
                # Obtener símbolos configurados
                symbols = self.config.get('symbols', {})
                all_symbols = symbols.get('crypto', []) + symbols.get('stocks', [])
                
                if not all_symbols:
                    await asyncio.sleep(60)
                    continue
                
                # Obtener datos en tiempo real
                realtime_data = await self.data_manager.get_realtime_data(all_symbols)
                
                # Procesar datos y generar señales si es necesario
                for symbol, data in realtime_data.items():
                    if not data.empty:
                        # Aquí se podría generar señales automáticamente
                        # según configuración
                        pass
                
                # Esperar antes del siguiente ciclo
                await asyncio.sleep(10)  # 10 segundos
                
            except Exception as e:
                logger.error(f"Error en monitoreo del mercado: {e}")
                await asyncio.sleep(30)
    
    async def _strategy_evaluation_loop(self):
        """Loop de evaluación de estrategias"""
        logger.info("Iniciada evaluación de estrategias")
        
        while self.running:
            try:
                # Obtener símbolos y datos
                symbols = self.config.get('symbols', {})
                all_symbols = symbols.get('crypto', []) + symbols.get('stocks', [])
                
                for symbol in all_symbols:
                    try:
                        # Obtener datos históricos recientes
                        end_date = datetime.now()
                        start_date = end_date - timedelta(days=1)  # Último día
                        
                        historical_data = await self.data_manager.get_historical_data(
                            symbol=symbol,
                            timeframe='1h',
                            start_date=start_date,
                            end_date=end_date
                        )
                        
                        if not historical_data.empty:
                            # Obtener señales de ensemble
                            signal, confidence, metadata = await self.strategy_manager.get_ensemble_signal(
                                symbol, historical_data
                            )
                            
                            # Si la señal es fuerte, podría generar alerta
                            if confidence > 0.8:
                                await self.alert_manager.create_alert(
                                    title=f"Señal {signal.signal_type.value} para {symbol}",
                                    message=f"Confianza: {confidence:.2%}, Fuerza: {signal.strength:.2f}",
                                    symbol=symbol,
                                    metadata={
                                        'signal_type': signal.signal_type.value,
                                        'confidence': confidence,
                                        'strength': signal.strength,
                                        'ensemble_metadata': metadata
                                    }
                                )
                                
                    except Exception as e:
                        logger.error(f"Error evaluando estrategias para {symbol}: {e}")
                
                # Esperar antes del siguiente ciclo
                await asyncio.sleep(300)  # 5 minutos
                
            except Exception as e:
                logger.error(f"Error en loop de estrategias: {e}")
                await asyncio.sleep(60)
    
    async def _alert_trigger_loop(self):
        """Loop de verificación de triggers de alertas"""
        logger.info("Iniciado loop de triggers de alertas")
        
        while self.running:
            try:
                # Obtener datos de mercado actuales
                market_data = await self._get_current_market_data()
                
                # Verificar triggers
                await self.alert_manager.check_triggers(market_data)
                
                # Esperar antes del siguiente ciclo
                await asyncio.sleep(60)  # 1 minuto
                
            except Exception as e:
                logger.error(f"Error en loop de triggers: {e}")
                await asyncio.sleep(30)
    
    async def _health_check_loop(self):
        """Loop de health checks"""
        while self.running:
            try:
                await self.health_checker.perform_health_checks()
                await asyncio.sleep(60)  # 1 minuto
                
            except Exception as e:
                logger.error(f"Error en health check: {e}")
                await asyncio.sleep(30)
    
    async def _get_current_market_data(self) -> Dict[str, Any]:
        """Obtiene datos actuales del mercado para triggers"""
        symbols = self.config.get('symbols', {})
        all_symbols = symbols.get('crypto', []) + symbols.get('stocks', [])
        
        market_data = {}
        
        for symbol in all_symbols[:5]:  # Limitar a 5 símbolos para evitar rate limits
            try:
                realtime_data = await self.data_manager.get_realtime_data([symbol])
                if symbol in realtime_data and not realtime_data[symbol].empty:
                    latest = realtime_data[symbol].iloc[-1]
                    market_data[symbol] = {
                        'price': latest['close'],
                        'volume': latest['volume'],
                        'timestamp': latest['timestamp']
                    }
            except Exception as e:
                logger.error(f"Error obteniendo datos para {symbol}: {e}")
        
        return market_data
    
    async def stop(self):
        """Detiene el sistema de trading"""
        if not self.running:
            return
        
        logger.info("Deteniendo sistema de trading...")
        self.running = False
        
        try:
            # Cancelar tareas de background
            for task in self.background_tasks:
                task.cancel()
            
            # Esperar que terminen las tareas
            if self.background_tasks:
                await asyncio.gather(*self.background_tasks, return_exceptions=True)
            
            # Detener componentes
            await self.data_manager.stop_realtime_feeds()
            await self.alert_manager.stop()
            await self.data_manager.cleanup()
            
            logger.info("Sistema detenido exitosamente")
            
        except Exception as e:
            logger.error(f"Error deteniendo sistema: {e}")
    
    def run_server(self):
        """Ejecuta el servidor API"""
        api_config = self.config.get('api', {})
        
        uvicorn.run(
            self.app,
            host=api_config.get('host', '0.0.0.0'),
            port=api_config.get('port', 8000),
            workers=api_config.get('workers', 1),
            log_level=self.config.get('app', {}).get('log_level', 'INFO').lower()
        )

# Instancia global del sistema
trading_system = None

async def startup_handler():
    """Handler de startup para FastAPI"""
    global trading_system
    if trading_system:
        await trading_system.start()

async def shutdown_handler():
    """Handler de shutdown para FastAPI"""
    global trading_system
    if trading_system:
        await trading_system.stop()

def signal_handler(signum, frame):
    """Handler para señales del sistema"""
    logger.info(f"Recibida señal {signum}, iniciando shutdown...")
    asyncio.create_task(shutdown_handler())
    sys.exit(0)

async def main():
    """Función principal"""
    global trading_system
    
    # Configurar handlers de señales
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Crear e inicializar sistema
        trading_system = TradingSystem()
        await trading_system.initialize()
        
        # Configurar eventos de FastAPI
        trading_system.app.add_event_handler("startup", startup_handler)
        trading_system.app.add_event_handler("shutdown", shutdown_handler)
        
        # Ejecutar servidor
        logger.info("Iniciando servidor API...")
        trading_system.run_server()
        
    except KeyboardInterrupt:
        logger.info("Interrupción por teclado recibida")
    except Exception as e:
        logger.error(f"Error en main: {e}")
        raise
    finally:
        if trading_system:
            await trading_system.stop()

if __name__ == "__main__":
    asyncio.run(main())