"""
Drift Protocol Connection Manager
Handles all interactions with Drift trading protocol
"""

import asyncio
import logging
from typing import Dict, List, Optional, Union
from decimal import Decimal
import time

# Drift SDK imports
from driftpy.drift_client import DriftClient
from driftpy.drift_user import DriftUser
from driftpy.accounts import get_perp_market_account, get_spot_market_account
from driftpy.constants.config import configs
from driftpy.types import PositionDirection, OrderType, OrderParams

# Solana imports
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Commitment

# Utils
from dotenv import load_dotenv
import os
import yaml
import json

load_dotenv()

class DriftConnector:
    """
    High-level interface for Drift Protocol operations
    """
    
    def __init__(self, config_path: str = "config/drift_config.yaml"):
        self.config = self._load_config(config_path)
        self.logger = self._setup_logging()
        
        # Connection components
        self.connection: Optional[AsyncClient] = None
        self.drift_client: Optional[DriftClient] = None
        self.drift_user: Optional[DriftUser] = None
        self.wallet: Optional[Keypair] = None
        
        # Market data cache
        self.market_cache = {}
        self.last_cache_update = 0
        self.cache_ttl = 1  # 1 second cache
        
        # Connection status
        self.connected = False
        self.subscribed = False
        
    def _load_config(self, config_path: str) -> Dict:
        """Load configuration from YAML file"""
        try:
            with open(config_path, 'r') as file:
                return yaml.safe_load(file)
        except Exception as e:
            raise Exception(f"Failed to load config: {e}")
    
    def _setup_logging(self) -> logging.Logger:
        """Setup logging configuration"""
        logging.basicConfig(
            level=getattr(logging, self.config['monitoring']['log_level']),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        return logging.getLogger(__name__)
    
    async def connect(self) -> bool:
        """
        Establish connection to Drift Protocol
        """
        try:
            self.logger.info("Connecting to Drift Protocol...")
            
            # Setup wallet
            private_key = os.getenv('SOLANA_PRIVATE_KEY')
            if not private_key:
                raise ValueError("SOLANA_PRIVATE_KEY not found in environment")
            
            self.wallet = Keypair.from_base58_string(private_key)
            self.logger.info(f"Wallet loaded: {self.wallet.pubkey()}")
            
            # Setup RPC connection
            rpc_url = self.config['network']['rpc_endpoint']
            commitment = Commitment(self.config['network']['commitment'])
            self.connection = AsyncClient(rpc_url, commitment=commitment)
            
            # Initialize Drift client
            env = self.config['network']['environment']
            self.drift_client = DriftClient(
                connection=self.connection,
                wallet=self.wallet,
                env=env,
            )
            
            # Subscribe to drift client
            await self.drift_client.subscribe()
            self.subscribed = True
            
            # Initialize user account
            subaccount_id = self.config['drift']['subaccount_id']
            self.drift_user = DriftUser(
                drift_client=self.drift_client,
                user_public_key=self.wallet.pubkey(),
                subaccount_id=subaccount_id
            )
            
            await self.drift_user.subscribe()
            
            self.connected = True
            self.logger.info("✅ Successfully connected to Drift Protocol")
            
            # Log account info
            await self._log_account_info()
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to connect to Drift: {e}")
            self.connected = False
            return False
    
    async def disconnect(self):
        """Gracefully disconnect from Drift Protocol"""
        try:
            if self.drift_user:
                await self.drift_user.unsubscribe()
            if self.drift_client and self.subscribed:
                await self.drift_client.unsubscribe()
            
            self.connected = False
            self.subscribed = False
            self.logger.info("Disconnected from Drift Protocol")
            
        except Exception as e:
            self.logger.error(f"Error during disconnect: {e}")
    
    async def _log_account_info(self):
        """Log current account information"""
        try:
            user_account = self.drift_user.get_user_account()
            equity = await self.drift_user.get_total_collateral()
            
            self.logger.info(f"Account Authority: {user_account.authority}")
            self.logger.info(f"Subaccount ID: {user_account.sub_account_id}")
            self.logger.info(f"Total Equity: ${equity / 1e6:.2f}")
            
        except Exception as e:
            self.logger.error(f"Failed to log account info: {e}")
    
    async def get_market_data(self, market_index: int) -> Dict:
        """
        Get real-time market data for a specific market
        """
        current_time = time.time()
        cache_key = f"market_{market_index}"
        
        # Check cache first
        if (cache_key in self.market_cache and 
            current_time - self.last_cache_update < self.cache_ttl):
            return self.market_cache[cache_key]
        
        try:
            # Get perp market account
            perp_market = await get_perp_market_account(
                self.drift_client.program, 
                market_index
            )
            
            # Extract relevant data
            market_data = {
                'market_index': market_index,
                'oracle_price': float(perp_market.amm.last_oracle_price) / 1e6,
                'mark_price': float(perp_market.amm.last_mark_price_twap) / 1e6,
                'funding_rate': float(perp_market.amm.last_funding_rate) / 1e9,
                'open_interest': float(perp_market.amm.base_asset_amount_with_amm) / 1e9,
                'volume_24h': float(perp_market.amm.quote_asset_amount) / 1e6,
                'bid_ask_spread': self._calculate_spread(perp_market),
                'timestamp': current_time
            }
            
            # Update cache
            self.market_cache[cache_key] = market_data
            self.last_cache_update = current_time
            
            return market_data
            
        except Exception as e:
            self.logger.error(f"Failed to get market data for index {market_index}: {e}")
            return {}
    
    def _calculate_spread(self, perp_market) -> float:
        """Calculate bid-ask spread from market data"""
        try:
            # This is a simplified spread calculation
            # In reality, you'd need to access the orderbook
            oracle_price = float(perp_market.amm.last_oracle_price) / 1e6
            return oracle_price * 0.0001  # Assume 0.01% spread
        except:
            return 0.0
    
    async def get_position(self, market_index: int) -> Dict:
        """
        Get current position for a specific market
        """
        try:
            user_account = self.drift_user.get_user_account()
            
            for position in user_account.perp_positions:
                if position.market_index == market_index:
                    return {
                        'market_index': market_index,
                        'base_asset_amount': float(position.base_asset_amount) / 1e9,
                        'quote_asset_amount': float(position.quote_asset_amount) / 1e6,
                        'open_orders': position.open_orders,
                        'open_bids': float(position.open_bids) / 1e9,
                        'open_asks': float(position.open_asks) / 1e9,
                        'unsettled_pnl': float(position.unsettled_pnl) / 1e6,
                    }
            
            # No position found
            return {
                'market_index': market_index,
                'base_asset_amount': 0.0,
                'quote_asset_amount': 0.0,
                'open_orders': 0,
                'open_bids': 0.0,
                'open_asks': 0.0,
                'unsettled_pnl': 0.0,
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get position for market {market_index}: {e}")
            return {}
    
    async def place_order(self, 
                         market_index: int,
                         direction: str,  # "long" or "short"
                         amount: float,
                         order_type: str = "market",
                         price: Optional[float] = None) -> bool:
        """
        Place an order on Drift Protocol
        """
        try:
            # Convert direction to PositionDirection
            if direction.lower() == "long":
                position_direction = PositionDirection.LONG
            elif direction.lower() == "short":
                position_direction = PositionDirection.SHORT
            else:
                raise ValueError(f"Invalid direction: {direction}")
            
            # Convert order type
            if order_type.lower() == "market":
                drift_order_type = OrderType.MARKET
            elif order_type.lower() == "limit":
                drift_order_type = OrderType.LIMIT
            else:
                raise ValueError(f"Invalid order type: {order_type}")
            
            # Convert amount to base asset units
            base_asset_amount = int(amount * 1e9)
            
            # Create order params
            order_params = OrderParams(
                order_type=drift_order_type,
                market_index=market_index,
                direction=position_direction,
                base_asset_amount=base_asset_amount,
                price=int(price * 1e6) if price else 0,
            )
            
            # Place the order
            tx_sig = await self.drift_client.place_perp_order(order_params)
            
            self.logger.info(f"✅ Order placed: {direction} {amount} on market {market_index}")
            self.logger.info(f"Transaction signature: {tx_sig}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to place order: {e}")
            return False
    
    async def close_position(self, market_index: int) -> bool:
        """
        Close current position for a specific market
        """
        try:
            position = await self.get_position(market_index)
            
            if position['base_asset_amount'] == 0:
                self.logger.info(f"No position to close for market {market_index}")
                return True
            
            # Determine direction to close
            if position['base_asset_amount'] > 0:
                direction = "short"  # Close long position
            else:
                direction = "long"   # Close short position
            
            amount = abs(position['base_asset_amount'])
            
            return await self.place_order(
                market_index=market_index,
                direction=direction,
                amount=amount,
                order_type="market"
            )
            
        except Exception as e:
            self.logger.error(f"Failed to close position: {e}")
            return False
    
    async def get_account_summary(self) -> Dict:
        """
        Get comprehensive account summary
        """
        try:
            equity = await self.drift_user.get_total_collateral()
            unrealized_pnl = await self.drift_user.get_unrealized_pnl()
            free_collateral = await self.drift_user.get_free_collateral()
            
            return {
                'total_equity': float(equity) / 1e6,
                'unrealized_pnl': float(unrealized_pnl) / 1e6,
                'free_collateral': float(free_collateral) / 1e6,
                'leverage': await self.drift_user.get_leverage(),
                'timestamp': time.time()
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get account summary: {e}")
            return {}
    
    async def get_funding_rates(self) -> Dict[int, float]:
        """
        Get funding rates for all markets
        """
        funding_rates = {}
        
        try:
            # Get funding rates for configured markets
            for asset_config in self.config['trading']['preferred_assets']:
                market_index = asset_config['market_index']
                market_data = await self.get_market_data(market_index)
                
                if market_data:
                    funding_rates[market_index] = market_data['funding_rate']
            
            return funding_rates
            
        except Exception as e:
            self.logger.error(f"Failed to get funding rates: {e}")
            return {}

# Example usage and testing
async def test_drift_connection():
    """Test the Drift connection"""
    connector = DriftConnector()
    
    try:
        # Connect
        success = await connector.connect()
        if not success:
            print("❌ Failed to connect")
            return
        
        # Get account summary
        summary = await connector.get_account_summary()
        print(f"📊 Account Summary: {summary}")
        
        # Get market data for SOL-PERP
        market_data = await connector.get_market_data(0)  # SOL-PERP
        print(f"📈 SOL-PERP Data: {market_data}")
        
        # Get current position
        position = await connector.get_position(0)
        print(f"📍 Current Position: {position}")
        
        # Get funding rates
        funding_rates = await connector.get_funding_rates()
        print(f"💰 Funding Rates: {funding_rates}")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
    
    finally:
        await connector.disconnect()

if __name__ == "__main__":
    asyncio.run(test_drift_connection())