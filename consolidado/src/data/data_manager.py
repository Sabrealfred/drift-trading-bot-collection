"""
DataManager - Controlador principal de la capa de datos
Integra todas las fuentes de datos y procesamiento
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

from .connectors.base_connector import BaseConnector
from .connectors.binance_connector import BinanceConnector
from .connectors.alpaca_connector import AlpacaConnector
from .connectors.yahoo_connector import YahooConnector
from .processors.data_processor import DataProcessor
from .processors.feature_engine import FeatureEngine
from .storage.data_storage import DataStorage

logger = logging.getLogger(__name__)

class DataManager:
    """
    Gestor central de todos los datos del sistema
    Maneja múltiples fuentes, procesamiento y almacenamiento
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.connectors: Dict[str, BaseConnector] = {}
        self.processor = DataProcessor(config)
        self.feature_engine = FeatureEngine(config)
        self.storage = DataStorage(config)
        
        # Inicializar conectores según configuración
        self._init_connectors()
        
        # Cache para datos en tiempo real
        self.realtime_cache = {}
        
    def _init_connectors(self):
        """Inicializa conectores según configuración"""
        connector_configs = self.config.get('data_sources', {})
        
        for source_name, source_config in connector_configs.items():
            if not source_config.get('enabled', False):
                continue
                
            try:
                if source_name == 'binance':
                    self.connectors[source_name] = BinanceConnector(source_config)
                elif source_name == 'alpaca':
                    self.connectors[source_name] = AlpacaConnector(source_config)
                elif source_name == 'yahoo':
                    self.connectors[source_name] = YahooConnector(source_config)
                    
                logger.info(f"Conector {source_name} inicializado exitosamente")
                
            except Exception as e:
                logger.error(f"Error inicializando conector {source_name}: {e}")
    
    async def get_historical_data(
        self, 
        symbol: str, 
        timeframe: str, 
        start_date: datetime, 
        end_date: datetime,
        sources: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        Obtiene datos históricos de múltiples fuentes
        
        Args:
            symbol: Símbolo del activo (ej: 'BTCUSDT', 'AAPL')
            timeframe: Marco temporal ('1m', '5m', '1h', '1d')
            start_date: Fecha inicio
            end_date: Fecha fin
            sources: Lista de fuentes a usar (None = todas)
            
        Returns:
            DataFrame con datos históricos procesados
        """
        if sources is None:
            sources = list(self.connectors.keys())
            
        all_data = []
        
        for source in sources:
            if source not in self.connectors:
                logger.warning(f"Fuente {source} no disponible")
                continue
                
            try:
                connector = self.connectors[source]
                data = await connector.get_historical_data(
                    symbol, timeframe, start_date, end_date
                )
                
                if not data.empty:
                    data['source'] = source
                    all_data.append(data)
                    logger.info(f"Datos históricos obtenidos de {source}: {len(data)} registros")
                    
            except Exception as e:
                logger.error(f"Error obteniendo datos de {source}: {e}")
        
        if not all_data:
            return pd.DataFrame()
            
        # Combinar datos de múltiples fuentes
        combined_data = self._combine_multi_source_data(all_data)
        
        # Procesar datos
        processed_data = self.processor.process_ohlcv_data(combined_data)
        
        # Generar features
        enhanced_data = self.feature_engine.generate_features(processed_data)
        
        # Guardar en storage
        await self.storage.save_historical_data(symbol, timeframe, enhanced_data)
        
        return enhanced_data
    
    async def get_realtime_data(self, symbols: List[str]) -> Dict[str, pd.DataFrame]:
        """
        Obtiene datos en tiempo real para múltiples símbolos
        
        Args:
            symbols: Lista de símbolos a monitorear
            
        Returns:
            Diccionario con datos en tiempo real por símbolo
        """
        realtime_data = {}
        
        for symbol in symbols:
            symbol_data = []
            
            for source_name, connector in self.connectors.items():
                try:
                    data = await connector.get_realtime_data(symbol)
                    if data is not None and not data.empty:
                        data['source'] = source_name
                        symbol_data.append(data)
                        
                except Exception as e:
                    logger.error(f"Error datos tiempo real {source_name}/{symbol}: {e}")
            
            if symbol_data:
                # Combinar y procesar datos
                combined = self._combine_multi_source_data(symbol_data)
                processed = self.processor.process_realtime_data(combined)
                enhanced = self.feature_engine.generate_realtime_features(processed)
                
                realtime_data[symbol] = enhanced
                
                # Actualizar cache
                self.realtime_cache[symbol] = enhanced
                
        return realtime_data
    
    def _combine_multi_source_data(self, data_list: List[pd.DataFrame]) -> pd.DataFrame:
        """
        Combina datos de múltiples fuentes con resolución de conflictos
        
        Args:
            data_list: Lista de DataFrames de diferentes fuentes
            
        Returns:
            DataFrame combinado y limpio
        """
        if not data_list:
            return pd.DataFrame()
            
        if len(data_list) == 1:
            return data_list[0]
        
        # Estrategia de combinación basada en prioridad y calidad
        combined = pd.concat(data_list, ignore_index=True)
        
        # Eliminar duplicados manteniendo el mejor dato
        combined = combined.sort_values(['timestamp', 'source'])
        combined = combined.drop_duplicates(subset=['timestamp'], keep='first')
        
        # Ordenar por timestamp
        combined = combined.sort_values('timestamp').reset_index(drop=True)
        
        return combined
    
    async def get_market_data_summary(self) -> Dict[str, Any]:
        """
        Obtiene resumen del estado del mercado
        
        Returns:
            Diccionario con métricas del mercado
        """
        summary = {
            'active_sources': len(self.connectors),
            'cached_symbols': len(self.realtime_cache),
            'last_update': datetime.now(),
            'sources_status': {}
        }
        
        for source_name, connector in self.connectors.items():
            try:
                status = await connector.get_status()
                summary['sources_status'][source_name] = status
            except Exception as e:
                summary['sources_status'][source_name] = {'error': str(e)}
        
        return summary
    
    async def start_realtime_feeds(self, symbols: List[str]):
        """Inicia feeds de datos en tiempo real"""
        for source_name, connector in self.connectors.items():
            try:
                await connector.start_realtime_feed(symbols)
                logger.info(f"Feed tiempo real iniciado en {source_name}")
            except Exception as e:
                logger.error(f"Error iniciando feed {source_name}: {e}")
    
    async def stop_realtime_feeds(self):
        """Detiene todos los feeds de tiempo real"""
        for source_name, connector in self.connectors.items():
            try:
                await connector.stop_realtime_feed()
                logger.info(f"Feed tiempo real detenido en {source_name}")
            except Exception as e:
                logger.error(f"Error deteniendo feed {source_name}: {e}")
    
    async def cleanup(self):
        """Limpieza de recursos"""
        await self.stop_realtime_feeds()
        await self.storage.close()
        logger.info("DataManager: recursos liberados")