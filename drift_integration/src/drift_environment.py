"""
Drift Environment for Deep Reinforcement Learning Trading
Integrates the original DRL bot with Drift Protocol for live trading
"""

import asyncio
import numpy as np
import pandas as pd
import time
from typing import Dict, List, Tuple, Optional
from decimal import Decimal
import logging

# Import original Environment
import sys
import os
sys.path.append('../repos/repos/Trading-Bot---Deep-Reinforcement-Learning/Bot_code_and_models')
from Environment import Environment as OriginalEnvironment

# Import our Drift connector
from drift_connector import DriftConnector

class DriftEnvironment(OriginalEnvironment):
    """
    Enhanced Environment that connects to Drift Protocol for live trading
    Extends the original Environment with real-time data and trading capabilities
    """
    
    def __init__(self, 
                 drift_connector: DriftConnector,
                 market_index: int = 0,  # SOL-PERP by default
                 reward_type: str = "profit",  # "profit", "sr", "aggressive_profit"
                 live_mode: bool = False,
                 config_path: str = "config/drift_config.yaml"):
        
        # Store Drift-specific attributes
        self.drift_connector = drift_connector
        self.market_index = market_index
        self.live_mode = live_mode
        self.config = self._load_config(config_path)
        
        # Setup logging
        self.logger = logging.getLogger(__name__)
        
        # Trading state
        self.current_position_size = 0.0  # Current position in base asset
        self.entry_price = 0.0
        self.last_trade_time = 0
        self.total_fees_paid = 0.0
        
        # Risk management
        self.daily_pnl = 0.0
        self.max_drawdown = 0.0
        self.peak_equity = 1000.0  # Starting equity
        self.consecutive_losses = 0
        
        # Real-time data buffers
        self.price_buffer = []
        self.volume_buffer = []
        self.funding_rate_buffer = []
        self.features_buffer = []
        self.buffer_size = 100  # Keep last 100 data points
        
        # Initialize with dummy data for parent class
        dummy_df = pd.DataFrame({
            'Open': [100], 'High': [100], 'Low': [100], 'Close': [100]
        })
        
        # Initialize parent class
        super().__init__(dummy_df, reward_type)
        
        # Override with enhanced reward function
        self.reward_f = reward_type
        self._setup_enhanced_rewards()
        
        self.logger.info(f"✅ DriftEnvironment initialized for market {market_index}")
    
    def _load_config(self, config_path: str) -> Dict:
        """Load configuration"""
        import yaml
        try:
            with open(config_path, 'r') as file:
                return yaml.safe_load(file)
        except Exception as e:
            self.logger.error(f"Failed to load config: {e}")
            return {}
    
    def _setup_enhanced_rewards(self):
        """Setup enhanced reward functions for high-performance trading"""
        self.reward_configs = {
            "profit": {
                "base_multiplier": 1.0,
                "timing_bonus": 2.0,
                "loss_penalty": -1.5,
                "funding_bonus": 0.5
            },
            "sr": {  # Sharpe Ratio optimized
                "base_multiplier": 0.8,
                "volatility_penalty": -0.3,
                "consistency_bonus": 1.2,
                "drawdown_penalty": -2.0
            },
            "aggressive_profit": {  # For 900% target
                "base_multiplier": 3.0,
                "leverage_bonus": 1.5,
                "momentum_bonus": 2.5,
                "loss_penalty": -3.0,
                "compound_bonus": 1.8
            }
        }
    
    async def get_real_time_state(self) -> np.ndarray:
        """
        Get current market state from Drift Protocol
        """
        try:
            # Get market data
            market_data = await self.drift_connector.get_market_data(self.market_index)
            if not market_data:
                return self._get_dummy_state()
            
            # Get account data
            account_summary = await self.drift_connector.get_account_summary()
            position = await self.drift_connector.get_position(self.market_index)
            
            # Get funding rates
            funding_rates = await self.drift_connector.get_funding_rates()
            current_funding = funding_rates.get(self.market_index, 0.0)
            
            # Update buffers
            self._update_buffers(market_data, current_funding)
            
            # Extract features
            features = self._extract_advanced_features(
                market_data, account_summary, position, current_funding
            )
            
            return np.array(features, dtype=np.float32)
            
        except Exception as e:
            self.logger.error(f"Failed to get real-time state: {e}")
            return self._get_dummy_state()
    
    def _update_buffers(self, market_data: Dict, funding_rate: float):
        """Update data buffers with new information"""
        current_price = market_data.get('oracle_price', 0.0)
        current_volume = market_data.get('volume_24h', 0.0)
        
        # Update price buffer
        self.price_buffer.append(current_price)
        if len(self.price_buffer) > self.buffer_size:
            self.price_buffer.pop(0)
        
        # Update volume buffer
        self.volume_buffer.append(current_volume)
        if len(self.volume_buffer) > self.buffer_size:
            self.volume_buffer.pop(0)
        
        # Update funding rate buffer
        self.funding_rate_buffer.append(funding_rate)
        if len(self.funding_rate_buffer) > self.buffer_size:
            self.funding_rate_buffer.pop(0)
    
    def _extract_advanced_features(self, 
                                 market_data: Dict,
                                 account_summary: Dict,
                                 position: Dict,
                                 funding_rate: float) -> List[float]:
        """
        Extract comprehensive features for DRL model
        """
        features = []
        
        try:
            # 1. Price features (8 features)
            current_price = market_data.get('oracle_price', 0.0)
            mark_price = market_data.get('mark_price', current_price)
            
            if len(self.price_buffer) >= 2:
                price_change_1 = (current_price - self.price_buffer[-2]) / self.price_buffer[-2]
                price_volatility = np.std(self.price_buffer[-20:]) if len(self.price_buffer) >= 20 else 0.0
                price_momentum_5 = (current_price - self.price_buffer[-5]) / self.price_buffer[-5] if len(self.price_buffer) >= 5 else 0.0
                price_momentum_20 = (current_price - self.price_buffer[-20]) / self.price_buffer[-20] if len(self.price_buffer) >= 20 else 0.0
            else:
                price_change_1 = price_volatility = price_momentum_5 = price_momentum_20 = 0.0
            
            features.extend([
                current_price / 1000.0,  # Normalized price
                mark_price / 1000.0,
                price_change_1,
                price_volatility,
                price_momentum_5,
                price_momentum_20,
                (mark_price - current_price) / current_price if current_price > 0 else 0.0,  # Mark-oracle spread
                market_data.get('bid_ask_spread', 0.0) / current_price if current_price > 0 else 0.0  # Spread %
            ])
            
            # 2. Volume and liquidity features (4 features)
            current_volume = market_data.get('volume_24h', 0.0)
            open_interest = market_data.get('open_interest', 0.0)
            
            volume_change = 0.0
            volume_trend = 0.0
            if len(self.volume_buffer) >= 2:
                volume_change = (current_volume - self.volume_buffer[-2]) / self.volume_buffer[-2] if self.volume_buffer[-2] > 0 else 0.0
                if len(self.volume_buffer) >= 10:
                    recent_vol = np.mean(self.volume_buffer[-5:])
                    older_vol = np.mean(self.volume_buffer[-10:-5])
                    volume_trend = (recent_vol - older_vol) / older_vol if older_vol > 0 else 0.0
            
            features.extend([
                current_volume / 1000000.0,  # Normalized volume
                volume_change,
                volume_trend,
                open_interest / 1000000.0  # Normalized OI
            ])
            
            # 3. Funding rate features (4 features)
            funding_rate_change = 0.0
            funding_trend = 0.0
            avg_funding = 0.0
            
            if len(self.funding_rate_buffer) >= 2:
                funding_rate_change = funding_rate - self.funding_rate_buffer[-2]
                avg_funding = np.mean(self.funding_rate_buffer)
                if len(self.funding_rate_buffer) >= 10:
                    recent_funding = np.mean(self.funding_rate_buffer[-5:])
                    older_funding = np.mean(self.funding_rate_buffer[-10:-5])
                    funding_trend = recent_funding - older_funding
            
            features.extend([
                funding_rate * 1000,  # Scale up funding rate
                funding_rate_change * 1000,
                funding_trend * 1000,
                avg_funding * 1000
            ])
            
            # 4. Position and account features (8 features)
            total_equity = account_summary.get('total_equity', 1000.0)
            unrealized_pnl = account_summary.get('unrealized_pnl', 0.0)
            free_collateral = account_summary.get('free_collateral', 1000.0)
            leverage = account_summary.get('leverage', 0.0)
            
            position_size = position.get('base_asset_amount', 0.0)
            position_pnl = position.get('unsettled_pnl', 0.0)
            
            features.extend([
                total_equity / 1000.0,  # Normalized equity
                unrealized_pnl / 100.0,  # Normalized PnL
                free_collateral / 1000.0,  # Normalized collateral
                leverage / 10.0,  # Normalized leverage
                position_size,  # Position size
                position_pnl / 100.0,  # Position PnL
                (total_equity - self.peak_equity) / self.peak_equity,  # Drawdown
                self.consecutive_losses / 10.0  # Consecutive losses
            ])
            
            # 5. Technical indicators (8 features)
            if len(self.price_buffer) >= 20:
                prices = np.array(self.price_buffer)
                
                # RSI
                rsi = self._calculate_rsi(prices)
                
                # MACD
                macd, macd_signal = self._calculate_macd(prices)
                
                # Bollinger Bands
                bb_upper, bb_lower, bb_middle = self._calculate_bollinger_bands(prices)
                bb_position = (current_price - bb_lower) / (bb_upper - bb_lower) if (bb_upper - bb_lower) > 0 else 0.5
                
                # Moving averages
                sma_20 = np.mean(prices[-20:])
                sma_50 = np.mean(prices[-50:]) if len(prices) >= 50 else sma_20
                
                features.extend([
                    rsi / 100.0,  # Normalized RSI
                    macd / current_price if current_price > 0 else 0.0,  # Normalized MACD
                    macd_signal / current_price if current_price > 0 else 0.0,  # Normalized MACD signal
                    bb_position,  # BB position
                    (current_price - sma_20) / sma_20 if sma_20 > 0 else 0.0,  # Price vs SMA20
                    (current_price - sma_50) / sma_50 if sma_50 > 0 else 0.0,  # Price vs SMA50
                    (sma_20 - sma_50) / sma_50 if sma_50 > 0 else 0.0,  # SMA cross
                    (bb_upper - bb_lower) / bb_middle if bb_middle > 0 else 0.0  # BB width
                ])
            else:
                # Not enough data for technical indicators
                features.extend([0.5, 0.0, 0.0, 0.5, 0.0, 0.0, 0.0, 0.0])
            
            # Ensure we have exactly 32 features
            while len(features) < 32:
                features.append(0.0)
            
            return features[:32]
            
        except Exception as e:
            self.logger.error(f"Error extracting features: {e}")
            return [0.0] * 32
    
    def _calculate_rsi(self, prices: np.ndarray, period: int = 14) -> float:
        """Calculate RSI indicator"""
        if len(prices) < period + 1:
            return 50.0
        
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def _calculate_macd(self, prices: np.ndarray) -> Tuple[float, float]:
        """Calculate MACD indicator"""
        if len(prices) < 26:
            return 0.0, 0.0
        
        ema_12 = self._calculate_ema(prices, 12)
        ema_26 = self._calculate_ema(prices, 26)
        macd = ema_12 - ema_26
        
        # Simple approximation for signal line
        macd_signal = macd * 0.9  # Simplified
        
        return macd, macd_signal
    
    def _calculate_ema(self, prices: np.ndarray, period: int) -> float:
        """Calculate Exponential Moving Average"""
        if len(prices) < period:
            return np.mean(prices)
        
        alpha = 2.0 / (period + 1)
        ema = prices[0]
        
        for price in prices[1:]:
            ema = alpha * price + (1 - alpha) * ema
        
        return ema
    
    def _calculate_bollinger_bands(self, prices: np.ndarray, period: int = 20, std_dev: float = 2.0) -> Tuple[float, float, float]:
        """Calculate Bollinger Bands"""
        if len(prices) < period:
            mean_price = np.mean(prices)
            return mean_price, mean_price, mean_price
        
        recent_prices = prices[-period:]
        middle = np.mean(recent_prices)
        std = np.std(recent_prices)
        
        upper = middle + (std_dev * std)
        lower = middle - (std_dev * std)
        
        return upper, lower, middle
    
    def _get_dummy_state(self) -> np.ndarray:
        """Return dummy state when real data is unavailable"""
        return np.zeros(32, dtype=np.float32)
    
    async def execute_action(self, action: int) -> Tuple[np.ndarray, float, bool]:
        """
        Execute trading action in Drift Protocol
        
        Args:
            action: 0=Hold, 1=Long, 2=Short
            
        Returns:
            next_state, reward, done
        """
        try:
            # Get current state before action
            current_state = await self.get_real_time_state()
            
            # Execute action if in live mode
            if self.live_mode:
                success = await self._execute_live_action(action)
                if not success:
                    self.logger.warning(f"Failed to execute action {action}")
            
            # Wait for next tick (simulate time passage)
            await asyncio.sleep(1)  # 1 second between actions
            
            # Get new state after action
            next_state = await self.get_real_time_state()
            
            # Calculate reward
            reward = await self._calculate_enhanced_reward(action, current_state, next_state)
            
            # Check if episode should end
            done = await self._check_episode_end()
            
            return next_state, reward, done
            
        except Exception as e:
            self.logger.error(f"Error executing action: {e}")
            return self._get_dummy_state(), -1.0, False
    
    async def _execute_live_action(self, action: int) -> bool:
        """Execute the actual trade on Drift Protocol"""
        try:
            if action == 0:  # Hold
                return True
            
            # Get position size from config
            asset_config = None
            for config in self.config['trading']['preferred_assets']:
                if config['market_index'] == self.market_index:
                    asset_config = config
                    break
            
            if not asset_config:
                self.logger.error(f"No config found for market {self.market_index}")
                return False
            
            # Calculate position size
            account_summary = await self.drift_connector.get_account_summary()
            equity = account_summary.get('total_equity', 1000.0)
            position_size_usd = equity * asset_config['position_size_pct']
            
            # Get current price to calculate base asset amount
            market_data = await self.drift_connector.get_market_data(self.market_index)
            current_price = market_data.get('oracle_price', 100.0)
            position_size_base = position_size_usd / current_price
            
            # Apply leverage
            leverage = min(asset_config['max_leverage'], 
                          self.config['trading']['risk_management']['max_daily_loss_pct'] * 20)
            position_size_base *= leverage
            
            if action == 1:  # Long
                return await self.drift_connector.place_order(
                    market_index=self.market_index,
                    direction="long",
                    amount=position_size_base,
                    order_type="market"
                )
            elif action == 2:  # Short
                return await self.drift_connector.place_order(
                    market_index=self.market_index,
                    direction="short", 
                    amount=position_size_base,
                    order_type="market"
                )
            
            return False
            
        except Exception as e:
            self.logger.error(f"Failed to execute live action: {e}")
            return False
    
    async def _calculate_enhanced_reward(self, action: int, prev_state: np.ndarray, current_state: np.ndarray) -> float:
        """
        Calculate enhanced reward based on multiple factors
        """
        try:
            reward_config = self.reward_configs.get(self.reward_f, self.reward_configs["profit"])
            
            # Base reward from price movement
            if len(prev_state) >= 2 and len(current_state) >= 2:
                prev_price = prev_state[0] * 1000.0  # Denormalize
                current_price = current_state[0] * 1000.0
                price_change = (current_price - prev_price) / prev_price if prev_price > 0 else 0.0
            else:
                price_change = 0.0
            
            # Calculate base reward based on action and price movement
            base_reward = 0.0
            if action == 1:  # Long
                base_reward = price_change
            elif action == 2:  # Short  
                base_reward = -price_change
            # action == 0 (Hold) gets 0 base reward
            
            # Apply reward multiplier
            base_reward *= reward_config["base_multiplier"]
            
            # Timing bonus for good entries
            if abs(price_change) > 0.01:  # Significant move
                if (action == 1 and price_change > 0) or (action == 2 and price_change < 0):
                    base_reward *= reward_config.get("timing_bonus", 1.0)
            
            # Loss penalty
            if (action == 1 and price_change < -0.005) or (action == 2 and price_change > 0.005):
                base_reward *= reward_config.get("loss_penalty", 1.0)
                self.consecutive_losses += 1
            else:
                self.consecutive_losses = 0
            
            # Funding rate consideration
            if len(current_state) >= 16:  # Funding rate feature
                funding_rate = current_state[12] / 1000.0  # Denormalize
                if action == 2 and funding_rate > 0.0001:  # Short with positive funding
                    base_reward += funding_rate * reward_config.get("funding_bonus", 0.0)
            
            # Additional rewards for aggressive profit strategy
            if self.reward_f == "aggressive_profit":
                # Leverage bonus
                if len(current_state) >= 20:
                    leverage = current_state[19] * 10.0  # Denormalize
                    if leverage > 3.0 and base_reward > 0:
                        base_reward *= (1 + leverage * 0.1)
                
                # Momentum bonus
                if len(current_state) >= 8:
                    momentum_5 = current_state[4]
                    momentum_20 = current_state[5]
                    if abs(momentum_5) > 0.02 and abs(momentum_20) > 0.05:
                        if (action == 1 and momentum_5 > 0) or (action == 2 and momentum_5 < 0):
                            base_reward *= reward_config.get("momentum_bonus", 1.0)
            
            # Risk penalties
            if len(current_state) >= 24:
                drawdown = current_state[22]
                if drawdown < -0.1:  # 10% drawdown
                    base_reward -= abs(drawdown) * 2
            
            # Normalize reward
            base_reward = np.clip(base_reward, -1.0, 1.0)
            
            return float(base_reward)
            
        except Exception as e:
            self.logger.error(f"Error calculating reward: {e}")
            return 0.0
    
    async def _check_episode_end(self) -> bool:
        """
        Check if trading episode should end based on risk management
        """
        try:
            # Check consecutive losses
            max_consecutive = self.config['targets']['max_consecutive_losses']
            if self.consecutive_losses >= max_consecutive:
                self.logger.warning(f"Stopping due to {self.consecutive_losses} consecutive losses")
                return True
            
            # Check daily loss limit
            account_summary = await self.drift_connector.get_account_summary()
            current_equity = account_summary.get('total_equity', 1000.0)
            daily_loss_pct = (self.peak_equity - current_equity) / self.peak_equity
            
            max_daily_loss = self.config['trading']['risk_management']['max_daily_loss_pct']
            if daily_loss_pct > max_daily_loss:
                self.logger.warning(f"Daily loss limit reached: {daily_loss_pct:.2%}")
                return True
            
            # Check emergency stop loss
            emergency_stop = self.config['trading']['risk_management']['emergency_stop_loss_pct']
            if daily_loss_pct > emergency_stop:
                self.logger.error(f"EMERGENCY STOP triggered: {daily_loss_pct:.2%}")
                return True
            
            # Update peak equity
            if current_equity > self.peak_equity:
                self.peak_equity = current_equity
            
            return False
            
        except Exception as e:
            self.logger.error(f"Error checking episode end: {e}")
            return False
    
    async def reset(self) -> np.ndarray:
        """Reset environment for new episode"""
        try:
            # Reset internal state
            self.consecutive_losses = 0
            self.daily_pnl = 0.0
            
            # Update peak equity
            account_summary = await self.drift_connector.get_account_summary()
            self.peak_equity = account_summary.get('total_equity', 1000.0)
            
            # Clear buffers partially (keep some history)
            if len(self.price_buffer) > 50:
                self.price_buffer = self.price_buffer[-50:]
            if len(self.volume_buffer) > 50:
                self.volume_buffer = self.volume_buffer[-50:]
            if len(self.funding_rate_buffer) > 50:
                self.funding_rate_buffer = self.funding_rate_buffer[-50:]
            
            # Get initial state
            initial_state = await self.get_real_time_state()
            
            self.logger.info("Environment reset for new episode")
            return initial_state
            
        except Exception as e:
            self.logger.error(f"Error resetting environment: {e}")
            return self._get_dummy_state()

# Example usage
async def test_drift_environment():
    """Test the Drift environment"""
    from drift_connector import DriftConnector
    
    # Create connector
    connector = DriftConnector()
    success = await connector.connect()
    
    if not success:
        print("❌ Failed to connect to Drift")
        return
    
    try:
        # Create environment
        env = DriftEnvironment(
            drift_connector=connector,
            market_index=0,  # SOL-PERP
            reward_type="aggressive_profit",
            live_mode=False  # Set to True for live trading
        )
        
        # Test getting state
        state = await env.get_real_time_state()
        print(f"📊 Current state shape: {state.shape}")
        print(f"📊 State values: {state[:10]}...")  # First 10 features
        
        # Test action execution
        next_state, reward, done = await env.execute_action(1)  # Long
        print(f"📈 Action executed - Reward: {reward:.4f}, Done: {done}")
        
        # Test reset
        reset_state = await env.reset()
        print(f"🔄 Environment reset - State shape: {reset_state.shape}")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
    
    finally:
        await connector.disconnect()

if __name__ == "__main__":
    asyncio.run(test_drift_environment())