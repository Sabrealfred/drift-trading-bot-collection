"""
Binance Connector - Conector para Binance Exchange
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import pandas as pd
import ccxt.async_support as ccxt

from .base_connector import BaseConnector

logger = logging.getLogger(__name__)

class BinanceConnector(BaseConnector):
    """Conector para Binance Exchange usando CCXT"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = config.get('api_key')
        self.api_secret = config.get('api_secret')
        self.sandbox = config.get('sandbox', True)
        self.testnet = config.get('testnet', True)
        
    async def connect(self) -> bool:
        """Establece conexión con Binance"""
        try:
            self._client = ccxt.binance({
                'apiKey': self.api_key,
                'secret': self.api_secret,
                'sandbox': self.sandbox,
                'enableRateLimit': True,
                'timeout': 30000,
            })
            
            if self.testnet:
                self._client.set_sandbox_mode(True)
            
            # Test de conexión
            await self._client.load_markets()
            logger.info("Conectado a Binance exitosamente")
            return True
            
        except Exception as e:
            logger.error(f"Error conectando a Binance: {e}")
            return False
    
    async def disconnect(self):
        """Cierra conexión con Binance"""
        if self._client:
            await self._client.close()
            logger.info("Desconectado de Binance")
    
    async def get_historical_data(
        self, 
        symbol: str, 
        timeframe: str, 
        start_date: datetime, 
        end_date: datetime
    ) -> pd.DataFrame:
        """
        Obtiene datos históricos de Binance
        
        Args:
            symbol: Par de trading (ej: 'BTC/USDT')
            timeframe: Timeframe ('1m', '5m', '1h', '1d')
            start_date: Fecha inicio
            end_date: Fecha fin
            
        Returns:
            DataFrame con datos OHLCV
        """
        if not self._client:
            await self.connect()
        
        if not self._validate_symbol(symbol) or not self._validate_timeframe(timeframe):
            raise ValueError("Símbolo o timeframe inválido")
        
        try:
            # Convertir fechas a timestamp
            since = int(start_date.timestamp() * 1000)
            until = int(end_date.timestamp() * 1000)
            
            all_data = []
            current_since = since
            
            # Binance tiene límite de 1000 candles por request
            while current_since < until:
                ohlcv = await self._client.fetch_ohlcv(
                    symbol=symbol,
                    timeframe=timeframe,
                    since=current_since,
                    limit=1000
                )
                
                if not ohlcv:
                    break
                
                all_data.extend(ohlcv)
                
                # Actualizar timestamp para siguiente batch
                current_since = ohlcv[-1][0] + 1
                
                # Evitar rate limiting
                await asyncio.sleep(0.1)
            
            # Filtrar datos hasta end_date
            filtered_data = [
                candle for candle in all_data 
                if candle[0] <= until
            ]
            
            return self._create_ohlcv_dataframe(filtered_data)
            
        except Exception as e:
            logger.error(f"Error obteniendo datos históricos de Binance: {e}")
            return pd.DataFrame()
    
    async def get_realtime_data(self, symbol: str) -> pd.DataFrame:
        """
        Obtiene último ticker de Binance
        
        Args:
            symbol: Par de trading
            
        Returns:
            DataFrame con último precio
        """
        if not self._client:
            await self.connect()
        
        try:
            ticker = await self._client.fetch_ticker(symbol)
            
            # Crear DataFrame con datos actuales
            current_time = datetime.now()
            data = [[
                int(current_time.timestamp() * 1000),
                ticker['open'],
                ticker['high'], 
                ticker['low'],
                ticker['last'],
                ticker['baseVolume']
            ]]
            
            return self._create_ohlcv_dataframe(data)
            
        except Exception as e:
            logger.error(f"Error obteniendo datos en tiempo real de Binance: {e}")
            return pd.DataFrame()
    
    async def get_symbols(self) -> List[str]:
        """Obtiene lista de símbolos disponibles en Binance"""
        if not self._client:
            await self.connect()
        
        try:
            markets = await self._client.load_markets()
            return list(markets.keys())
            
        except Exception as e:
            logger.error(f"Error obteniendo símbolos de Binance: {e}")
            return []
    
    async def get_status(self) -> Dict[str, Any]:
        """Obtiene estado de la conexión con Binance"""
        if not self._client:
            return {'connected': False, 'error': 'No conectado'}
        
        try:
            # Test simple de conectividad
            await self._client.fetch_time()
            
            return {
                'connected': True,
                'exchange': 'Binance',
                'sandbox': self.sandbox,
                'testnet': self.testnet,
                'timestamp': datetime.now(),
                'rate_limit': self._client.rateLimit
            }
            
        except Exception as e:
            return {
                'connected': False,
                'error': str(e),
                'timestamp': datetime.now()
            }
    
    async def get_account_info(self) -> Dict[str, Any]:
        """
        Obtiene información de la cuenta (requiere API keys)
        
        Returns:
            Diccionario con info de cuenta y balances
        """
        if not self._client:
            await self.connect()
        
        if not self.api_key or not self.api_secret:
            raise ValueError("API keys requeridas para info de cuenta")
        
        try:
            balance = await self._client.fetch_balance()
            
            return {
                'total_balance_usdt': balance.get('USDT', {}).get('total', 0),
                'free_balance_usdt': balance.get('USDT', {}).get('free', 0),
                'balances': {
                    asset: info for asset, info in balance.items() 
                    if info.get('total', 0) > 0
                },
                'timestamp': datetime.now()
            }
            
        except Exception as e:
            logger.error(f"Error obteniendo info de cuenta Binance: {e}")
            raise
    
    async def place_order(
        self, 
        symbol: str, 
        order_type: str, 
        side: str, 
        amount: float, 
        price: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Coloca orden en Binance (solo para trading activo)
        
        Args:
            symbol: Par de trading
            order_type: 'market', 'limit', 'stop'
            side: 'buy' o 'sell'
            amount: Cantidad
            price: Precio (para órdenes limit)
            
        Returns:
            Información de la orden creada
        """
        if not self._client:
            await self.connect()
        
        if not self.api_key or not self.api_secret:
            raise ValueError("API keys requeridas para trading")
        
        try:
            order = await self._client.create_order(
                symbol=symbol,
                type=order_type,
                side=side,
                amount=amount,
                price=price
            )
            
            logger.info(f"Orden creada: {order['id']} - {side} {amount} {symbol}")
            return order
            
        except Exception as e:
            logger.error(f"Error creando orden en Binance: {e}")
            raise