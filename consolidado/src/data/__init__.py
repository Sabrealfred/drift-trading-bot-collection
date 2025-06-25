"""
Data Layer - Sistema de gestión de datos unificado
"""

from .data_manager import DataManager
from .connectors import *
from .processors import *
from .storage import *

__all__ = [
    'DataManager',
    'BinanceConnector',
    'AlpacaConnector', 
    'YahooConnector',
    'DataProcessor',
    'FeatureEngine',
    'DataStorage'
]