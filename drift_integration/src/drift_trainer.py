"""
Drift Trading Bot Trainer
Main training script for the aggressive DRL trading bot
"""

import asyncio
import numpy as np
import pandas as pd
import time
import logging
from typing import Dict, List, Tuple
import yaml
from datetime import datetime, timedelta
import os
import json

# Local imports
from drift_connector import DriftConnector
from drift_environment import DriftEnvironment
from aggressive_agent import AggressiveAgent

class DriftTrainer:
    """
    Main trainer class for Drift trading bot
    """
    
    def __init__(self, config_path: str = "config/drift_config.yaml"):
        self.config = self._load_config(config_path)
        self.logger = self._setup_logging()
        
        # Initialize components
        self.drift_connector = None
        self.environment = None
        self.agent = None
        
        # Training parameters
        self.max_episodes = 1000
        self.max_steps_per_episode = 500
        self.eval_frequency = 50
        self.save_frequency = 100
        
        # Performance tracking
        self.episode_rewards = []
        self.episode_lengths = []
        self.evaluation_results = []
        self.training_start_time = None
        
        # Risk management
        self.emergency_stop = False
        self.max_consecutive_losses = self.config['targets']['max_consecutive_losses']
        self.consecutive_losses = 0
        
        self.logger.info("✅ DriftTrainer initialized")
    
    def _load_config(self, config_path: str) -> Dict:
        """Load configuration"""
        try:
            with open(config_path, 'r') as file:
                return yaml.safe_load(file)
        except Exception as e:
            raise Exception(f"Failed to load config: {e}")
    
    def _setup_logging(self) -> logging.Logger:
        """Setup logging"""
        logging.basicConfig(
            level=getattr(logging, self.config['monitoring']['log_level']),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('drift_training.log'),
                logging.StreamHandler()
            ]
        )
        return logging.getLogger(__name__)
    
    async def initialize(self) -> bool:
        """
        Initialize all components
        """
        try:
            self.logger.info("🚀 Initializing Drift Trading Bot...")
            
            # Initialize Drift connector
            self.drift_connector = DriftConnector()
            success = await self.drift_connector.connect()
            
            if not success:
                self.logger.error("❌ Failed to connect to Drift Protocol")
                return False
            
            # Initialize environment
            preferred_asset = self.config['trading']['preferred_assets'][0]
            market_index = preferred_asset['market_index']
            
            self.environment = DriftEnvironment(
                drift_connector=self.drift_connector,
                market_index=market_index,
                reward_type="aggressive_profit",  # For 900% target
                live_mode=False,  # Start with simulation
                config_path="config/drift_config.yaml"
            )
            
            # Initialize agent
            self.agent = AggressiveAgent()
            
            self.logger.info("✅ All components initialized successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Initialization failed: {e}")
            return False
    
    async def train_episode(self, episode: int) -> Tuple[float, int, Dict]:
        """
        Train one episode
        """
        episode_reward = 0.0
        episode_steps = 0
        episode_info = {
            'actions': [],
            'rewards': [],
            'q_values': [],
            'losses': []
        }
        
        try:
            # Reset environment
            state = await self.environment.reset()
            done = False
            
            while not done and episode_steps < self.max_steps_per_episode:
                # Select action
                action = self.agent.select_action(state, training=True)
                episode_info['actions'].append(action)
                
                # Execute action
                next_state, reward, done = await self.environment.execute_action(action)
                
                # Store transition
                self.agent.store_transition(state, action, reward, next_state, done)
                
                # Train agent
                if episode_steps % 4 == 0:  # Train every 4 steps
                    loss = self.agent.train_step()
                    if loss > 0:
                        episode_info['losses'].append(loss)
                
                # Update target network
                if self.agent.steps_done % self.agent.target_update == 0:
                    self.agent.update_target_network()
                
                # Track metrics
                episode_reward += reward
                episode_info['rewards'].append(reward)
                
                # Update state
                state = next_state
                episode_steps += 1
                
                # Emergency stop check
                if self.emergency_stop:
                    self.logger.warning("🛑 Emergency stop triggered")
                    done = True
                    break
                
                # Small delay to avoid overwhelming the API
                await asyncio.sleep(0.1)
            
            # Episode completed
            self.episode_rewards.append(episode_reward)
            self.episode_lengths.append(episode_steps)
            
            # Update consecutive losses
            if episode_reward < 0:
                self.consecutive_losses += 1
            else:
                self.consecutive_losses = 0
            
            # Check for emergency stop conditions
            if self.consecutive_losses >= self.max_consecutive_losses:
                self.logger.warning(f"🛑 {self.consecutive_losses} consecutive losses - triggering emergency stop")
                self.emergency_stop = True
            
            return episode_reward, episode_steps, episode_info
            
        except Exception as e:
            self.logger.error(f"Error in training episode {episode}: {e}")
            return 0.0, 0, episode_info
    
    async def evaluate_agent(self, num_episodes: int = 5) -> Dict:
        """
        Evaluate agent performance
        """
        self.logger.info(f"📊 Evaluating agent over {num_episodes} episodes...")
        
        eval_rewards = []
        eval_lengths = []
        eval_actions = []
        
        for episode in range(num_episodes):
            try:
                episode_reward = 0.0
                episode_steps = 0
                episode_actions = []
                
                # Reset environment
                state = await self.environment.reset()
                done = False
                
                while not done and episode_steps < self.max_steps_per_episode:
                    # Select action (no exploration)
                    action = self.agent.select_action(state, training=False)
                    episode_actions.append(action)
                    
                    # Execute action
                    next_state, reward, done = await self.environment.execute_action(action)
                    
                    episode_reward += reward
                    episode_steps += 1
                    state = next_state
                    
                    await asyncio.sleep(0.1)
                
                eval_rewards.append(episode_reward)
                eval_lengths.append(episode_steps)
                eval_actions.extend(episode_actions)
                
            except Exception as e:
                self.logger.error(f"Error in evaluation episode {episode}: {e}")
                continue
        
        # Calculate evaluation metrics
        avg_reward = np.mean(eval_rewards) if eval_rewards else 0.0
        std_reward = np.std(eval_rewards) if eval_rewards else 0.0
        avg_length = np.mean(eval_lengths) if eval_lengths else 0.0
        
        # Action distribution
        action_counts = np.bincount(eval_actions, minlength=3)
        action_dist = action_counts / len(eval_actions) if eval_actions else [0.33, 0.33, 0.33]
        
        eval_results = {
            'avg_reward': avg_reward,
            'std_reward': std_reward,
            'avg_length': avg_length,
            'action_distribution': {
                'hold': action_dist[0],
                'long': action_dist[1],
                'short': action_dist[2]
            },
            'total_episodes': len(eval_rewards)
        }
        
        self.evaluation_results.append(eval_results)
        
        self.logger.info(f"📊 Evaluation Results:")
        self.logger.info(f"   Average Reward: {avg_reward:.4f} ± {std_reward:.4f}")
        self.logger.info(f"   Average Length: {avg_length:.1f} steps")
        self.logger.info(f"   Action Distribution: Hold={action_dist[0]:.2%}, Long={action_dist[1]:.2%}, Short={action_dist[2]:.2%}")
        
        return eval_results
    
    async def save_checkpoint(self, episode: int, eval_results: Dict = None):
        """
        Save training checkpoint
        """
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            checkpoint_dir = f"checkpoints/episode_{episode}_{timestamp}"
            os.makedirs(checkpoint_dir, exist_ok=True)
            
            # Save agent model
            model_path = os.path.join(checkpoint_dir, "model.pth")
            metadata = {
                'episode': episode,
                'total_episodes': len(self.episode_rewards),
                'avg_reward_last_100': np.mean(self.episode_rewards[-100:]) if len(self.episode_rewards) >= 100 else np.mean(self.episode_rewards),
                'evaluation_results': eval_results,
                'training_time': time.time() - self.training_start_time if self.training_start_time else 0
            }
            self.agent.save_model(model_path, metadata)
            
            # Save training statistics
            stats_path = os.path.join(checkpoint_dir, "training_stats.json")
            training_stats = {
                'episode_rewards': self.episode_rewards,
                'episode_lengths': self.episode_lengths,
                'evaluation_results': self.evaluation_results,
                'agent_stats': self.agent.get_training_stats(),
                'config': self.config
            }
            
            with open(stats_path, 'w') as f:
                json.dump(training_stats, f, indent=2)
            
            self.logger.info(f"💾 Checkpoint saved to {checkpoint_dir}")
            
        except Exception as e:
            self.logger.error(f"Failed to save checkpoint: {e}")
    
    async def run_training(self, live_mode: bool = False):
        """
        Main training loop
        """
        self.training_start_time = time.time()
        self.logger.info(f"🎯 Starting training for {self.max_episodes} episodes")
        self.logger.info(f"🎯 Target: {self.config['targets']['annual_return_target']*100:.0f}% annual return")
        
        if live_mode:
            self.logger.warning("⚠️  LIVE MODE ENABLED - Real money at risk!")
            self.environment.live_mode = True
        
        best_performance = -float('inf')
        
        for episode in range(1, self.max_episodes + 1):
            try:
                # Train episode
                episode_reward, episode_steps, episode_info = await self.train_episode(episode)
                
                # Log progress
                avg_reward_100 = np.mean(self.episode_rewards[-100:]) if len(self.episode_rewards) >= 100 else np.mean(self.episode_rewards)
                
                self.logger.info(f"Episode {episode:4d} | "
                               f"Reward: {episode_reward:8.4f} | "
                               f"Steps: {episode_steps:3d} | "
                               f"Avg100: {avg_reward_100:8.4f} | "
                               f"ε: {self.agent.epsilon:.3f}")
                
                # Evaluate periodically
                if episode % self.eval_frequency == 0:
                    eval_results = await self.evaluate_agent()
                    
                    # Check for improvement
                    if eval_results['avg_reward'] > best_performance:
                        best_performance = eval_results['avg_reward']
                        self.agent.best_performance = best_performance
                        
                        # Save best model
                        await self.save_checkpoint(episode, eval_results)
                        self.logger.info(f"🏆 New best performance: {best_performance:.4f}")
                    
                    # Update learning rate
                    self.agent.scheduler.step(eval_results['avg_reward'])
                
                # Save checkpoint periodically
                if episode % self.save_frequency == 0:
                    await self.save_checkpoint(episode)
                
                # Check emergency stop
                if self.emergency_stop:
                    self.logger.warning(f"🛑 Training stopped at episode {episode} due to emergency conditions")
                    break
                
                # Check if target performance reached
                if avg_reward_100 > 0.5:  # Adjust threshold based on target
                    self.logger.info(f"🎯 Target performance reached at episode {episode}!")
                    break
                    
            except KeyboardInterrupt:
                self.logger.info("⌨️  Training interrupted by user")
                break
            except Exception as e:
                self.logger.error(f"❌ Error in episode {episode}: {e}")
                continue
        
        # Final evaluation and save
        self.logger.info("🏁 Training completed!")
        
        final_eval = await self.evaluate_agent(num_episodes=10)
        await self.save_checkpoint(episode, final_eval)
        
        training_time = time.time() - self.training_start_time
        self.logger.info(f"⏱️  Total training time: {training_time/3600:.2f} hours")
        self.logger.info(f"🏆 Final performance: {final_eval['avg_reward']:.4f}")
        
        return final_eval
    
    async def backtest(self, start_date: str = None, end_date: str = None):
        """
        Run backtesting with historical data
        """
        self.logger.info("📈 Starting backtest...")
        
        # For now, use simple simulation
        # In production, you'd fetch historical data and replay it
        backtest_episodes = 50
        self.environment.live_mode = False
        
        backtest_results = await self.evaluate_agent(num_episodes=backtest_episodes)
        
        self.logger.info("📈 Backtest completed")
        self.logger.info(f"📊 Backtest Results: {backtest_results}")
        
        return backtest_results
    
    async def cleanup(self):
        """Cleanup resources"""
        try:
            if self.drift_connector:
                await self.drift_connector.disconnect()
            self.logger.info("🧹 Cleanup completed")
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")

async def main():
    """Main execution function"""
    trainer = DriftTrainer()
    
    try:
        # Initialize
        success = await trainer.initialize()
        if not success:
            return
        
        # Parse command line arguments or use defaults
        import sys
        
        if len(sys.argv) > 1:
            mode = sys.argv[1].lower()
        else:
            mode = "train"
        
        if mode == "train":
            print("🎯 Starting training mode...")
            results = await trainer.run_training(live_mode=False)
            
        elif mode == "live":
            print("⚠️  Starting LIVE trading mode...")
            print("⚠️  This will use real money!")
            
            confirm = input("Type 'CONFIRM' to proceed with live trading: ")
            if confirm == "CONFIRM":
                results = await trainer.run_training(live_mode=True)
            else:
                print("❌ Live trading cancelled")
                return
                
        elif mode == "backtest":
            print("📈 Starting backtest mode...")
            results = await trainer.backtest()
            
        elif mode == "eval":
            print("📊 Starting evaluation mode...")
            results = await trainer.evaluate_agent(num_episodes=10)
            
        else:
            print("❓ Unknown mode. Use: train, live, backtest, or eval")
            return
        
        print(f"✅ Completed with results: {results}")
        
    except KeyboardInterrupt:
        print("\n⌨️  Interrupted by user")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await trainer.cleanup()

if __name__ == "__main__":
    asyncio.run(main())