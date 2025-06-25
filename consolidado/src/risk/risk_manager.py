"""
Risk Manager - Controlador principal de gestión de riesgo
Integra todas las funciones de control de riesgo
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import pandas as pd
import numpy as np

from .position_sizer import PositionSizer
from .portfolio_manager import PortfolioManager  
from .risk_metrics import RiskMetrics

logger = logging.getLogger(__name__)

class RiskLevel(Enum):
    """Niveles de riesgo"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class RiskAssessment:
    """Evaluación de riesgo"""
    overall_risk: RiskLevel
    risk_score: float  # 0-100
    max_position_size: float
    stop_loss_level: Optional[float]
    take_profit_level: Optional[float]
    warnings: List[str]
    metadata: Dict[str, Any]

@dataclass
class TradeValidation:
    """Resultado de validación de trade"""
    approved: bool
    adjusted_size: Optional[float]
    stop_loss: Optional[float]
    take_profit: Optional[float]
    risk_reward_ratio: Optional[float]
    rejection_reason: Optional[str]
    warnings: List[str]

class RiskManager:
    """
    Gestor central de riesgo
    Valida trades, calcula position sizing y monitorea exposición
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        
        # Componentes especializados
        self.position_sizer = PositionSizer(config.get('position_sizing', {}))
        self.portfolio_manager = PortfolioManager(config.get('portfolio', {}))
        self.risk_metrics = RiskMetrics(config.get('metrics', {}))
        
        # Límites globales de riesgo
        self.max_portfolio_risk = config.get('max_portfolio_risk', 0.02)  # 2%
        self.max_single_position_risk = config.get('max_single_position_risk', 0.01)  # 1%
        self.max_daily_loss = config.get('max_daily_loss', 0.05)  # 5%
        self.max_drawdown = config.get('max_drawdown', 0.20)  # 20%
        
        # Configuración de stop-loss
        self.default_stop_loss_pct = config.get('default_stop_loss_pct', 0.02)  # 2%
        self.trailing_stop_enabled = config.get('trailing_stop_enabled', True)
        self.trailing_stop_distance = config.get('trailing_stop_distance', 0.01)  # 1%
        
        # Estado del portfolio
        self.current_positions = {}
        self.daily_pnl = 0.0
        self.max_drawdown_reached = 0.0
        
        # Historial de trades para análisis
        self.trade_history = []
        
    async def validate_trade(
        self,
        symbol: str,
        side: str,  # 'buy' or 'sell'
        intended_size: float,
        current_price: float,
        portfolio_value: float,
        current_positions: Dict[str, Any],
        market_data: pd.DataFrame
    ) -> TradeValidation:
        """
        Valida un trade propuesto considerando todos los aspectos de riesgo
        
        Args:
            symbol: Símbolo del activo
            side: 'buy' o 'sell'
            intended_size: Tamaño propuesto (en unidades de base currency)
            current_price: Precio actual
            portfolio_value: Valor total del portfolio
            current_positions: Posiciones actuales
            market_data: Datos de mercado para análisis
            
        Returns:
            TradeValidation con aprobación y ajustes
        """
        warnings = []
        
        try:
            # 1. Verificar límites básicos de portfolio
            portfolio_check = await self._check_portfolio_limits(
                portfolio_value, current_positions
            )
            if not portfolio_check['approved']:
                return TradeValidation(
                    approved=False,
                    adjusted_size=None,
                    stop_loss=None,
                    take_profit=None,
                    risk_reward_ratio=None,
                    rejection_reason=portfolio_check['reason'],
                    warnings=warnings
                )
            
            # 2. Calcular tamaño de posición óptimo
            risk_assessment = await self.assess_market_risk(symbol, market_data)
            
            optimal_size = self.position_sizer.calculate_position_size(
                portfolio_value=portfolio_value,
                risk_per_trade=self.max_single_position_risk,
                stop_loss_distance=self.default_stop_loss_pct,
                volatility=risk_assessment.metadata.get('volatility', 0.02)
            )
            
            # 3. Ajustar tamaño si es necesario
            final_size = min(intended_size, optimal_size)
            
            if final_size < intended_size:
                warnings.append(f"Tamaño reducido de {intended_size} a {final_size} por gestión de riesgo")
            
            # 4. Calcular stop-loss y take-profit
            stop_loss = self._calculate_stop_loss(current_price, side, risk_assessment)
            take_profit = self._calculate_take_profit(current_price, side, risk_assessment)
            
            # 5. Calcular ratio riesgo/beneficio
            risk_reward_ratio = self._calculate_risk_reward_ratio(
                current_price, stop_loss, take_profit, side
            )
            
            # 6. Verificar ratio mínimo
            min_risk_reward = self.config.get('min_risk_reward_ratio', 1.5)
            if risk_reward_ratio and risk_reward_ratio < min_risk_reward:
                warnings.append(f"Ratio riesgo/beneficio {risk_reward_ratio:.2f} menor al mínimo {min_risk_reward}")
            
            # 7. Verificaciones finales
            concentration_check = self._check_concentration_risk(
                symbol, final_size, current_price, portfolio_value, current_positions
            )
            
            if not concentration_check['approved']:
                return TradeValidation(
                    approved=False,
                    adjusted_size=None,
                    stop_loss=None,
                    take_profit=None,
                    risk_reward_ratio=None,
                    rejection_reason=concentration_check['reason'],
                    warnings=warnings
                )
            
            # 8. Verificar condiciones de mercado
            market_check = self._check_market_conditions(risk_assessment)
            if not market_check['approved']:
                warnings.extend(market_check['warnings'])
                
                # En condiciones adversas, reducir tamaño
                if risk_assessment.overall_risk in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
                    final_size *= 0.5
                    warnings.append("Tamaño reducido 50% por condiciones adversas de mercado")
            
            return TradeValidation(
                approved=True,
                adjusted_size=final_size,
                stop_loss=stop_loss,
                take_profit=take_profit,
                risk_reward_ratio=risk_reward_ratio,
                rejection_reason=None,
                warnings=warnings
            )
            
        except Exception as e:
            logger.error(f"Error validando trade: {e}")
            return TradeValidation(
                approved=False,
                adjusted_size=None,
                stop_loss=None,
                take_profit=None,
                risk_reward_ratio=None,
                rejection_reason=f"Error en validación: {str(e)}",
                warnings=warnings
            )
    
    async def _check_portfolio_limits(
        self, 
        portfolio_value: float, 
        current_positions: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Verifica límites globales del portfolio"""
        
        # Verificar pérdida diaria máxima
        if self.daily_pnl < -self.max_daily_loss * portfolio_value:
            return {
                'approved': False,
                'reason': f"Pérdida diaria máxima alcanzada: {self.daily_pnl:.2f}"
            }
        
        # Verificar drawdown máximo
        if self.max_drawdown_reached > self.max_drawdown:
            return {
                'approved': False,
                'reason': f"Drawdown máximo alcanzado: {self.max_drawdown_reached:.2%}"
            }
        
        # Verificar exposición total
        total_exposure = sum(
            pos.get('size', 0) * pos.get('price', 0) 
            for pos in current_positions.values()
        )
        
        max_exposure = portfolio_value * 0.95  # 95% máximo
        if total_exposure > max_exposure:
            return {
                'approved': False,
                'reason': f"Exposición total excede límite: {total_exposure:.2f} > {max_exposure:.2f}"
            }
        
        return {'approved': True}
    
    def _check_concentration_risk(
        self,
        symbol: str,
        size: float,
        price: float,
        portfolio_value: float,
        current_positions: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Verifica riesgo de concentración"""
        
        # Valor de la nueva posición
        position_value = size * price
        
        # Posición existente del mismo símbolo
        existing_position = current_positions.get(symbol, {})
        existing_value = existing_position.get('size', 0) * existing_position.get('price', 0)
        
        # Valor total de la posición después del trade
        total_position_value = existing_value + position_value
        
        # Verificar concentración por símbolo
        max_single_position_value = portfolio_value * self.config.get('max_single_position_pct', 0.20)
        
        if total_position_value > max_single_position_value:
            return {
                'approved': False,
                'reason': f"Concentración excesiva en {symbol}: {total_position_value:.2f} > {max_single_position_value:.2f}"
            }
        
        return {'approved': True}
    
    def _check_market_conditions(self, risk_assessment: RiskAssessment) -> Dict[str, Any]:
        """Verifica condiciones generales de mercado"""
        warnings = []
        
        if risk_assessment.overall_risk == RiskLevel.CRITICAL:
            warnings.append("Condiciones de mercado críticas - alto riesgo")
        elif risk_assessment.overall_risk == RiskLevel.HIGH:
            warnings.append("Condiciones de mercado adversas")
        
        return {
            'approved': True,
            'warnings': warnings
        }
    
    async def assess_market_risk(
        self, 
        symbol: str, 
        market_data: pd.DataFrame
    ) -> RiskAssessment:
        """
        Evalúa el riesgo actual del mercado para un símbolo
        
        Returns:
            RiskAssessment con evaluación completa
        """
        try:
            # Calcular métricas de riesgo
            volatility = self.risk_metrics.calculate_volatility(market_data['close'])
            sharpe_ratio = self.risk_metrics.calculate_sharpe_ratio(market_data['close'])
            max_drawdown = self.risk_metrics.calculate_max_drawdown(market_data['close'])
            var_95 = self.risk_metrics.calculate_var(market_data['close'], confidence=0.95)
            
            # Calcular score de riesgo (0-100)
            risk_score = self._calculate_risk_score(volatility, sharpe_ratio, max_drawdown, var_95)
            
            # Determinar nivel de riesgo
            if risk_score <= 25:
                risk_level = RiskLevel.LOW
            elif risk_score <= 50:
                risk_level = RiskLevel.MEDIUM
            elif risk_score <= 75:
                risk_level = RiskLevel.HIGH
            else:
                risk_level = RiskLevel.CRITICAL
            
            # Calcular tamaño máximo de posición basado en riesgo
            base_position_pct = self.config.get('base_position_pct', 0.05)
            risk_multiplier = {
                RiskLevel.LOW: 1.5,
                RiskLevel.MEDIUM: 1.0,
                RiskLevel.HIGH: 0.7,
                RiskLevel.CRITICAL: 0.3
            }
            
            max_position_size = base_position_pct * risk_multiplier[risk_level]
            
            # Generar warnings
            warnings = []
            if volatility > 0.05:  # 5% diario
                warnings.append(f"Alta volatilidad detectada: {volatility:.2%}")
            
            if max_drawdown > 0.15:  # 15%
                warnings.append(f"Drawdown significativo: {max_drawdown:.2%}")
            
            if sharpe_ratio < 0:
                warnings.append("Sharpe ratio negativo - rendimiento ajustado por riesgo pobre")
            
            return RiskAssessment(
                overall_risk=risk_level,
                risk_score=risk_score,
                max_position_size=max_position_size,
                stop_loss_level=None,  # Se calcula después
                take_profit_level=None,  # Se calcula después
                warnings=warnings,
                metadata={
                    'volatility': volatility,
                    'sharpe_ratio': sharpe_ratio,
                    'max_drawdown': max_drawdown,
                    'var_95': var_95,
                    'symbol': symbol,
                    'timestamp': datetime.now()
                }
            )
            
        except Exception as e:
            logger.error(f"Error evaluando riesgo de mercado: {e}")
            # Retornar evaluación conservadora en caso de error
            return RiskAssessment(
                overall_risk=RiskLevel.CRITICAL,
                risk_score=100,
                max_position_size=0.01,
                stop_loss_level=None,
                take_profit_level=None,
                warnings=[f"Error en evaluación de riesgo: {str(e)}"],
                metadata={'error': str(e)}
            )
    
    def _calculate_risk_score(
        self, 
        volatility: float, 
        sharpe_ratio: float, 
        max_drawdown: float, 
        var_95: float
    ) -> float:
        """
        Calcula score de riesgo combinado (0-100, donde 100 = máximo riesgo)
        """
        # Normalizar métricas a escala 0-1
        vol_score = min(volatility / 0.10, 1.0)  # >10% vol diaria = máximo
        drawdown_score = min(abs(max_drawdown) / 0.30, 1.0)  # >30% DD = máximo
        var_score = min(abs(var_95) / 0.05, 1.0)  # >5% VaR = máximo
        sharpe_score = max(0, 1 - (sharpe_ratio + 1) / 3)  # Sharpe 2+ = mínimo riesgo
        
        # Pesos para cada componente
        weights = {
            'volatility': 0.3,
            'drawdown': 0.25, 
            'var': 0.25,
            'sharpe': 0.2
        }
        
        # Score final ponderado
        total_score = (
            vol_score * weights['volatility'] +
            drawdown_score * weights['drawdown'] +
            var_score * weights['var'] +
            sharpe_score * weights['sharpe']
        )
        
        return total_score * 100
    
    def _calculate_stop_loss(
        self, 
        price: float, 
        side: str, 
        risk_assessment: RiskAssessment
    ) -> float:
        """Calcula nivel de stop-loss"""
        volatility = risk_assessment.metadata.get('volatility', 0.02)
        
        # Ajustar stop-loss basado en volatilidad
        stop_distance = max(self.default_stop_loss_pct, volatility * 1.5)
        
        if side == 'buy':
            return price * (1 - stop_distance)
        else:  # sell
            return price * (1 + stop_distance)
    
    def _calculate_take_profit(
        self, 
        price: float, 
        side: str, 
        risk_assessment: RiskAssessment
    ) -> Optional[float]:
        """Calcula nivel de take-profit"""
        default_tp_ratio = self.config.get('default_take_profit_ratio', 2.0)
        
        # Distancia del stop-loss
        stop_distance = max(self.default_stop_loss_pct, 
                          risk_assessment.metadata.get('volatility', 0.02) * 1.5)
        
        # Take-profit a múltiplo de la distancia del stop
        tp_distance = stop_distance * default_tp_ratio
        
        if side == 'buy':
            return price * (1 + tp_distance)
        else:  # sell
            return price * (1 - tp_distance)
    
    def _calculate_risk_reward_ratio(
        self, 
        price: float, 
        stop_loss: Optional[float], 
        take_profit: Optional[float], 
        side: str
    ) -> Optional[float]:
        """Calcula ratio riesgo/recompensa"""
        if not stop_loss or not take_profit:
            return None
        
        if side == 'buy':
            risk = price - stop_loss
            reward = take_profit - price
        else:  # sell
            risk = stop_loss - price
            reward = price - take_profit
        
        if risk <= 0:
            return None
        
        return reward / risk
    
    async def update_daily_pnl(self, pnl_change: float):
        """Actualiza P&L diario"""
        self.daily_pnl += pnl_change
    
    async def update_drawdown(self, current_drawdown: float):
        """Actualiza drawdown máximo"""
        self.max_drawdown_reached = max(self.max_drawdown_reached, current_drawdown)
    
    def get_risk_summary(self) -> Dict[str, Any]:
        """Obtiene resumen del estado de riesgo"""
        return {
            'daily_pnl': self.daily_pnl,
            'max_drawdown_reached': self.max_drawdown_reached,
            'max_daily_loss_limit': self.max_daily_loss,
            'max_drawdown_limit': self.max_drawdown,
            'max_portfolio_risk': self.max_portfolio_risk,
            'max_single_position_risk': self.max_single_position_risk,
            'total_trades_today': len([t for t in self.trade_history 
                                     if t.get('timestamp', datetime.min).date() == datetime.now().date()]),
            'risk_limits_breached': {
                'daily_loss': self.daily_pnl < -self.max_daily_loss,
                'max_drawdown': self.max_drawdown_reached > self.max_drawdown
            }
        }