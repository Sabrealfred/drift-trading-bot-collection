"""
Base Connector - Clase base para todos los conectores de datos
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from datetime import datetime
import pandas as pd

class BaseConnector(ABC):
    """Clase base para conectores de fuentes de datos"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.name = config.get('name', 'unknown')
        self.enabled = config.get('enabled', True)
        self.rate_limit = config.get('rate_limit', 100)  # requests per minute
        self._client = None
    
    @abstractmethod
    async def connect(self) -> bool:
        """Establece conexión con la fuente de datos"""
        pass
    
    @abstractmethod
    async def disconnect(self):
        """Cierra conexión con la fuente de datos"""
        pass
    
    @abstractmethod
    async def get_historical_data(
        self, 
        symbol: str, 
        timeframe: str, 
        start_date: datetime, 
        end_date: datetime
    ) -> pd.DataFrame:
        """
        Obtiene datos históricos
        
        Returns:
            DataFrame con columnas: timestamp, open, high, low, close, volume
        """
        pass
    
    @abstractmethod
    async def get_realtime_data(self, symbol: str) -> pd.DataFrame:
        """
        Obtiene datos en tiempo real
        
        Returns:
            DataFrame con último tick/candle
        """
        pass
    
    @abstractmethod
    async def get_symbols(self) -> List[str]:
        """Obtiene lista de símbolos disponibles"""
        pass
    
    @abstractmethod
    async def get_status(self) -> Dict[str, Any]:
        """Obtiene estado de la conexión"""
        pass
    
    async def start_realtime_feed(self, symbols: List[str]):
        """Inicia feed de datos en tiempo real (implementación opcional)"""
        pass
    
    async def stop_realtime_feed(self):
        """Detiene feed de datos en tiempo real (implementación opcional)"""
        pass
    
    def _validate_symbol(self, symbol: str) -> bool:
        """Valida formato del símbolo"""
        return isinstance(symbol, str) and len(symbol) > 0
    
    def _validate_timeframe(self, timeframe: str) -> bool:
        """Valida timeframe"""
        valid_timeframes = ['1m', '5m', '15m', '1h', '4h', '1d', '1w', '1M']
        return timeframe in valid_timeframes
    
    def _normalize_symbol(self, symbol: str) -> str:
        """Normaliza símbolo al formato del exchange"""
        return symbol.upper().replace('/', '')
    
    def _create_ohlcv_dataframe(self, data: List[List]) -> pd.DataFrame:
        """
        Crea DataFrame OHLCV estándar
        
        Args:
            data: Lista de [timestamp, open, high, low, close, volume]
        """
        if not data:
            return pd.DataFrame()
            
        df = pd.DataFrame(data, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume'
        ])
        
        # Convertir timestamp a datetime
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        
        # Convertir valores numéricos
        numeric_cols = ['open', 'high', 'low', 'close', 'volume']
        df[numeric_cols] = df[numeric_cols].astype(float)
        
        # Ordenar por timestamp
        df = df.sort_values('timestamp').reset_index(drop=True)
        
        return df