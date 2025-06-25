"""
Strategy Manager - Controlador principal de estrategias de trading
Maneja múltiples estrategias simultáneamente y combina señales
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import pandas as pd
import numpy as np
from dataclasses import dataclass
from enum import Enum

from .base_strategy import BaseStrategy, Signal, SignalType
from .rl_strategies.ppo_strategy import PPOStrategy
from .rl_strategies.dqn_strategy import DQNStrategy
from .ml_strategies.lstm_strategy import LSTMStrategy
from .technical_strategies.rsi_strategy import RSIStrategy
from .technical_strategies.macd_strategy import MACDStrategy

logger = logging.getLogger(__name__)

class EnsembleMethod(Enum):
    """Métodos de combinación de señales"""
    VOTING = "voting"          # Voto mayoritario
    WEIGHTED = "weighted"      # Promedio ponderado
    CONFIDENCE = "confidence"  # Basado en confianza
    BEST_PERFORMER = "best"    # Mejor performer histórico

@dataclass
class StrategyResult:
    """Resultado de una estrategia"""
    strategy_name: str
    signal: Signal
    confidence: float
    timestamp: datetime
    metadata: Dict[str, Any] = None

class StrategyManager:
    """
    Gestor central de estrategias de trading
    Ejecuta múltiples estrategias y combina señales
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.strategies: Dict[str, BaseStrategy] = {}
        self.ensemble_method = EnsembleMethod(
            config.get('ensemble_method', 'voting')
        )
        self.strategy_weights = config.get('strategy_weights', {})
        self.min_confidence = config.get('min_confidence', 0.6)
        
        # Métricas de performance por estrategia
        self.performance_metrics = {}
        
        # Cache de señales recientes
        self.signal_history = {}
        
        # Inicializar estrategias
        self._init_strategies()
    
    def _init_strategies(self):
        """Inicializa estrategias según configuración"""
        strategy_configs = self.config.get('strategies', {})
        
        for strategy_name, strategy_config in strategy_configs.items():
            if not strategy_config.get('enabled', False):
                continue
            
            try:
                strategy = self._create_strategy(strategy_name, strategy_config)
                if strategy:
                    self.strategies[strategy_name] = strategy
                    self.performance_metrics[strategy_name] = {
                        'total_signals': 0,
                        'correct_signals': 0,
                        'accuracy': 0.0,
                        'total_return': 0.0
                    }
                    logger.info(f"Estrategia {strategy_name} inicializada")
                    
            except Exception as e:
                logger.error(f"Error inicializando estrategia {strategy_name}: {e}")
    
    def _create_strategy(self, name: str, config: Dict[str, Any]) -> Optional[BaseStrategy]:
        """Factory para crear estrategias"""
        strategy_type = config.get('type', '').lower()
        
        strategy_map = {
            'ppo': PPOStrategy,
            'dqn': DQNStrategy,
            'lstm': LSTMStrategy,
            'rsi': RSIStrategy,
            'macd': MACDStrategy,
        }
        
        if strategy_type in strategy_map:
            return strategy_map[strategy_type](config)
        else:
            logger.warning(f"Tipo de estrategia desconocido: {strategy_type}")
            return None
    
    async def get_signals(
        self, 
        symbol: str, 
        data: pd.DataFrame,
        strategies: Optional[List[str]] = None
    ) -> Dict[str, StrategyResult]:
        """
        Obtiene señales de todas las estrategias para un símbolo
        
        Args:
            symbol: Símbolo del activo
            data: DataFrame con datos de mercado
            strategies: Lista de estrategias específicas (None = todas)
            
        Returns:
            Diccionario con resultados por estrategia
        """
        if strategies is None:
            strategies = list(self.strategies.keys())
        
        results = {}
        
        # Ejecutar estrategias en paralelo
        tasks = []
        for strategy_name in strategies:
            if strategy_name in self.strategies:
                task = self._get_strategy_signal(strategy_name, symbol, data)
                tasks.append((strategy_name, task))
        
        # Esperar resultados
        for strategy_name, task in tasks:
            try:
                signal, confidence, metadata = await task
                results[strategy_name] = StrategyResult(
                    strategy_name=strategy_name,
                    signal=signal,
                    confidence=confidence,
                    timestamp=datetime.now(),
                    metadata=metadata
                )
                
                # Actualizar historial
                if symbol not in self.signal_history:
                    self.signal_history[symbol] = {}
                self.signal_history[symbol][strategy_name] = results[strategy_name]
                
            except Exception as e:
                logger.error(f"Error ejecutando estrategia {strategy_name}: {e}")
        
        return results
    
    async def _get_strategy_signal(
        self, 
        strategy_name: str, 
        symbol: str, 
        data: pd.DataFrame
    ) -> Tuple[Signal, float, Dict[str, Any]]:
        """Ejecuta una estrategia específica"""
        strategy = self.strategies[strategy_name]
        
        # Preparar datos para la estrategia
        strategy_data = await strategy.prepare_data(data)
        
        # Obtener señal
        signal = await strategy.generate_signal(symbol, strategy_data)
        
        # Calcular confianza
        confidence = await strategy.calculate_confidence(symbol, strategy_data, signal)
        
        # Obtener metadata adicional
        metadata = await strategy.get_metadata(symbol, strategy_data)
        
        return signal, confidence, metadata
    
    async def get_ensemble_signal(
        self, 
        symbol: str, 
        data: pd.DataFrame
    ) -> Tuple[Signal, float, Dict[str, Any]]:
        """
        Combina señales de múltiples estrategias usando ensemble
        
        Returns:
            Señal combinada, confianza total y metadata
        """
        # Obtener señales individuales
        strategy_results = await self.get_signals(symbol, data)
        
        if not strategy_results:
            return Signal(SignalType.HOLD, 0, 0), 0.0, {}
        
        # Aplicar método de ensemble
        if self.ensemble_method == EnsembleMethod.VOTING:
            return self._voting_ensemble(strategy_results)
        elif self.ensemble_method == EnsembleMethod.WEIGHTED:
            return self._weighted_ensemble(strategy_results)
        elif self.ensemble_method == EnsembleMethod.CONFIDENCE:
            return self._confidence_ensemble(strategy_results)
        elif self.ensemble_method == EnsembleMethod.BEST_PERFORMER:
            return self._best_performer_ensemble(strategy_results)
        else:
            return self._voting_ensemble(strategy_results)
    
    def _voting_ensemble(
        self, 
        results: Dict[str, StrategyResult]
    ) -> Tuple[Signal, float, Dict[str, Any]]:
        """Ensemble por voto mayoritario"""
        buy_votes = 0
        sell_votes = 0
        hold_votes = 0
        total_confidence = 0.0
        
        for result in results.values():
            if result.confidence < self.min_confidence:
                hold_votes += 1
                continue
                
            if result.signal.signal_type == SignalType.BUY:
                buy_votes += 1
            elif result.signal.signal_type == SignalType.SELL:
                sell_votes += 1
            else:
                hold_votes += 1
            
            total_confidence += result.confidence
        
        # Determinar señal ganadora
        if buy_votes > sell_votes and buy_votes > hold_votes:
            signal_type = SignalType.BUY
            strength = buy_votes / len(results)
        elif sell_votes > buy_votes and sell_votes > hold_votes:
            signal_type = SignalType.SELL  
            strength = sell_votes / len(results)
        else:
            signal_type = SignalType.HOLD
            strength = hold_votes / len(results)
        
        avg_confidence = total_confidence / len(results) if results else 0.0
        
        signal = Signal(signal_type, strength, 1.0)  # Size por defecto
        
        metadata = {
            'method': 'voting',
            'buy_votes': buy_votes,
            'sell_votes': sell_votes, 
            'hold_votes': hold_votes,
            'strategies_used': list(results.keys())
        }
        
        return signal, avg_confidence, metadata
    
    def _weighted_ensemble(
        self, 
        results: Dict[str, StrategyResult]
    ) -> Tuple[Signal, float, Dict[str, Any]]:
        """Ensemble por promedio ponderado"""
        weighted_signal = 0.0
        total_weight = 0.0
        total_confidence = 0.0
        
        for strategy_name, result in results.items():
            if result.confidence < self.min_confidence:
                continue
            
            # Obtener peso de la estrategia
            weight = self.strategy_weights.get(strategy_name, 1.0)
            
            # Obtener performance histórico
            performance = self.performance_metrics.get(strategy_name, {})
            accuracy_weight = performance.get('accuracy', 0.5)
            
            # Peso final combina configuración y performance
            final_weight = weight * accuracy_weight * result.confidence
            
            # Convertir señal a valor numérico
            signal_value = 0.0
            if result.signal.signal_type == SignalType.BUY:
                signal_value = 1.0 * result.signal.strength
            elif result.signal.signal_type == SignalType.SELL:
                signal_value = -1.0 * result.signal.strength
            
            weighted_signal += signal_value * final_weight
            total_weight += final_weight
            total_confidence += result.confidence
        
        if total_weight == 0:
            signal = Signal(SignalType.HOLD, 0, 0)
            confidence = 0.0
        else:
            avg_signal = weighted_signal / total_weight
            avg_confidence = total_confidence / len(results)
            
            # Convertir valor numérico a señal
            if avg_signal > 0.1:
                signal = Signal(SignalType.BUY, abs(avg_signal), 1.0)
            elif avg_signal < -0.1:
                signal = Signal(SignalType.SELL, abs(avg_signal), 1.0)
            else:
                signal = Signal(SignalType.HOLD, 0, 0)
            
            confidence = avg_confidence
        
        metadata = {
            'method': 'weighted',
            'weighted_signal': weighted_signal,
            'total_weight': total_weight,
            'strategies_used': list(results.keys())
        }
        
        return signal, confidence, metadata
    
    def _confidence_ensemble(
        self, 
        results: Dict[str, StrategyResult]
    ) -> Tuple[Signal, float, Dict[str, Any]]:
        """Ensemble basado en confianza - usa la estrategia más confiada"""
        if not results:
            return Signal(SignalType.HOLD, 0, 0), 0.0, {}
        
        # Encontrar resultado con mayor confianza
        best_result = max(results.values(), key=lambda x: x.confidence)
        
        metadata = {
            'method': 'confidence',
            'best_strategy': best_result.strategy_name,
            'best_confidence': best_result.confidence,
            'all_confidences': {k: v.confidence for k, v in results.items()}
        }
        
        return best_result.signal, best_result.confidence, metadata
    
    def _best_performer_ensemble(
        self, 
        results: Dict[str, StrategyResult]
    ) -> Tuple[Signal, float, Dict[str, Any]]:
        """Ensemble basado en mejor performer histórico"""
        if not results:
            return Signal(SignalType.HOLD, 0, 0), 0.0, {}
        
        # Encontrar estrategia con mejor accuracy histórico
        best_strategy = None
        best_accuracy = 0.0
        
        for strategy_name in results.keys():
            metrics = self.performance_metrics.get(strategy_name, {})
            accuracy = metrics.get('accuracy', 0.0)
            
            if accuracy > best_accuracy:
                best_accuracy = accuracy
                best_strategy = strategy_name
        
        if best_strategy and best_strategy in results:
            best_result = results[best_strategy]
            metadata = {
                'method': 'best_performer',
                'best_strategy': best_strategy,
                'best_accuracy': best_accuracy
            }
            return best_result.signal, best_result.confidence, metadata
        
        # Fallback a voting si no hay histórico
        return self._voting_ensemble(results)
    
    async def update_performance(
        self, 
        strategy_name: str, 
        signal_was_correct: bool, 
        return_pct: float
    ):
        """Actualiza métricas de performance de una estrategia"""
        if strategy_name not in self.performance_metrics:
            return
        
        metrics = self.performance_metrics[strategy_name]
        metrics['total_signals'] += 1
        
        if signal_was_correct:
            metrics['correct_signals'] += 1
        
        metrics['accuracy'] = metrics['correct_signals'] / metrics['total_signals']
        metrics['total_return'] += return_pct
        
        logger.debug(f"Performance actualizada para {strategy_name}: "
                    f"accuracy={metrics['accuracy']:.2%}")
    
    def get_strategy_status(self) -> Dict[str, Any]:
        """Obtiene estado de todas las estrategias"""
        return {
            'total_strategies': len(self.strategies),
            'active_strategies': [name for name, strategy in self.strategies.items()],
            'ensemble_method': self.ensemble_method.value,
            'performance_metrics': self.performance_metrics,
            'last_update': datetime.now()
        }
    
    async def backtest_strategies(
        self, 
        symbol: str, 
        historical_data: pd.DataFrame
    ) -> Dict[str, Any]:
        """
        Ejecuta backtesting de todas las estrategias
        
        Returns:
            Resultados de backtesting por estrategia
        """
        backtest_results = {}
        
        for strategy_name, strategy in self.strategies.items():
            try:
                logger.info(f"Ejecutando backtest para {strategy_name}")
                results = await strategy.backtest(symbol, historical_data)
                backtest_results[strategy_name] = results
                
            except Exception as e:
                logger.error(f"Error en backtest de {strategy_name}: {e}")
                backtest_results[strategy_name] = {'error': str(e)}
        
        return backtest_results