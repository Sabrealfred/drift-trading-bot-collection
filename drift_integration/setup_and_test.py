#!/usr/bin/env python3
"""
Drift Trading Bot Setup and Test Script
Quick setup and testing for the Drift integration
"""

import asyncio
import os
import sys
import subprocess
import yaml
from pathlib import Path

def install_requirements():
    """Install required packages"""
    print("📦 Installing requirements...")
    
    try:
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", 
            "-r", "requirements_drift.txt"
        ])
        print("✅ Requirements installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install requirements: {e}")
        return False

def setup_environment():
    """Setup environment variables"""
    print("⚙️  Setting up environment...")
    
    # Check if .env exists
    if not os.path.exists('.env'):
        print("📝 Creating .env file from template...")
        if os.path.exists('.env.example'):
            with open('.env.example', 'r') as source:
                content = source.read()
            
            with open('.env', 'w') as target:
                target.write(content)
            
            print("📝 Please edit .env file with your Solana wallet private key")
            print("🔑 You can get a devnet wallet from: https://faucet.solana.com/")
            return False
        else:
            print("❌ No .env.example found")
            return False
    
    return True

def check_config():
    """Check configuration file"""
    print("📋 Checking configuration...")
    
    config_path = "config/drift_config.yaml"
    if not os.path.exists(config_path):
        print(f"❌ Config file not found: {config_path}")
        return False
    
    try:
        with open(config_path, 'r') as file:
            config = yaml.safe_load(file)
        
        # Validate essential config sections
        required_sections = ['network', 'drift', 'trading', 'model']
        for section in required_sections:
            if section not in config:
                print(f"❌ Missing config section: {section}")
                return False
        
        print("✅ Configuration is valid")
        return True
        
    except Exception as e:
        print(f"❌ Error reading config: {e}")
        return False

async def test_drift_connection():
    """Test connection to Drift Protocol"""
    print("🔗 Testing Drift connection...")
    
    try:
        # Add src to path
        sys.path.append('src')
        
        from drift_connector import DriftConnector
        
        # Test connection
        connector = DriftConnector()
        success = await connector.connect()
        
        if success:
            print("✅ Successfully connected to Drift Protocol")
            
            # Test basic functionality
            try:
                # Get account summary
                summary = await connector.get_account_summary()
                print(f"💰 Account equity: ${summary.get('total_equity', 0):.2f}")
                
                # Get market data
                market_data = await connector.get_market_data(0)  # SOL-PERP
                if market_data:
                    print(f"📈 SOL-PERP price: ${market_data.get('oracle_price', 0):.2f}")
                
                print("✅ Basic functionality test passed")
                
            except Exception as e:
                print(f"⚠️  Basic functionality test failed: {e}")
                print("   This might be due to insufficient devnet SOL or invalid keys")
            
            await connector.disconnect()
            return True
        else:
            print("❌ Failed to connect to Drift Protocol")
            print("   Please check your .env file and ensure you have:")
            print("   1. Valid Solana private key")
            print("   2. Sufficient devnet SOL")
            print("   3. Correct RPC endpoint")
            return False
            
    except Exception as e:
        print(f"❌ Connection test failed: {e}")
        return False

async def test_environment():
    """Test the DriftEnvironment"""
    print("🌍 Testing DriftEnvironment...")
    
    try:
        sys.path.append('src')
        
        from drift_connector import DriftConnector
        from drift_environment import DriftEnvironment
        
        # Create connector
        connector = DriftConnector()
        success = await connector.connect()
        
        if not success:
            print("❌ Cannot test environment without Drift connection")
            return False
        
        # Create environment
        env = DriftEnvironment(
            drift_connector=connector,
            market_index=0,  # SOL-PERP
            reward_type="aggressive_profit",
            live_mode=False
        )
        
        # Test state extraction
        state = await env.get_real_time_state()
        print(f"📊 State vector shape: {state.shape}")
        print(f"📊 Sample features: {state[:5]}")
        
        # Test action execution
        next_state, reward, done = await env.execute_action(0)  # Hold
        print(f"🎯 Action test - Reward: {reward:.4f}, Done: {done}")
        
        await connector.disconnect()
        print("✅ Environment test passed")
        return True
        
    except Exception as e:
        print(f"❌ Environment test failed: {e}")
        return False

async def test_agent():
    """Test the AggressiveAgent"""
    print("🤖 Testing AggressiveAgent...")
    
    try:
        sys.path.append('src')
        
        from aggressive_agent import AggressiveAgent
        
        # Create agent
        agent = AggressiveAgent()
        
        # Test action selection
        dummy_state = np.random.randn(32)
        action = agent.select_action(dummy_state, training=False)
        confidence = agent.get_action_confidence(dummy_state)
        
        print(f"🎯 Selected action: {action}")
        print(f"🎯 Action confidence: {confidence:.3f}")
        
        # Test training stats
        stats = agent.get_training_stats()
        print(f"📊 Agent stats: {stats}")
        
        print("✅ Agent test passed")
        return True
        
    except Exception as e:
        print(f"❌ Agent test failed: {e}")
        return False

def create_directory_structure():
    """Create necessary directories"""
    print("📁 Creating directory structure...")
    
    directories = [
        "checkpoints",
        "logs",
        "data",
        "models"
    ]
    
    for directory in directories:
        Path(directory).mkdir(exist_ok=True)
    
    print("✅ Directory structure created")

async def run_quick_demo():
    """Run a quick demo of the system"""
    print("🚀 Running quick demo...")
    
    try:
        sys.path.append('src')
        
        from drift_trainer import DriftTrainer
        
        # Create trainer
        trainer = DriftTrainer()
        
        # Initialize
        success = await trainer.initialize()
        if not success:
            print("❌ Failed to initialize trainer")
            return False
        
        print("🎯 Running 3 training episodes as demo...")
        
        # Run a few episodes
        for episode in range(1, 4):
            episode_reward, episode_steps, episode_info = await trainer.train_episode(episode)
            print(f"Episode {episode}: Reward={episode_reward:.4f}, Steps={episode_steps}")
        
        # Quick evaluation
        eval_results = await trainer.evaluate_agent(num_episodes=2)
        print(f"📊 Evaluation results: {eval_results}")
        
        await trainer.cleanup()
        print("✅ Demo completed successfully")
        return True
        
    except Exception as e:
        print(f"❌ Demo failed: {e}")
        return False

async def main():
    """Main setup and test function"""
    print("🚀 Drift Trading Bot Setup and Test")
    print("=" * 50)
    
    # Create directory structure
    create_directory_structure()
    
    # Check if we have numpy (for agent test)
    try:
        import numpy as np
        global np
    except ImportError:
        print("❌ NumPy not available")
        return
    
    # Check Python path setup
    current_dir = os.getcwd()
    if current_dir not in sys.path:
        sys.path.append(current_dir)
    
    # Step 1: Install requirements
    if not install_requirements():
        print("❌ Setup failed at requirements installation")
        return
    
    # Step 2: Setup environment
    if not setup_environment():
        print("⚠️  Please configure your .env file and run again")
        return
    
    # Step 3: Check configuration
    if not check_config():
        print("❌ Setup failed at configuration check")
        return
    
    # Step 4: Test components
    print("\n🧪 Running component tests...")
    
    # Test Drift connection
    drift_ok = await test_drift_connection()
    if not drift_ok:
        print("⚠️  Drift connection test failed - check your keys and network")
        print("   You can still test other components")
    
    # Test Agent (doesn't require network)
    agent_ok = await test_agent()
    
    # Test Environment (requires network)
    if drift_ok:
        env_ok = await test_environment()
    else:
        print("⏭️  Skipping environment test (no Drift connection)")
        env_ok = False
    
    # Step 5: Demo (if everything works)
    if drift_ok and agent_ok and env_ok:
        print("\n🎉 All tests passed! Running demo...")
        demo_ok = await run_quick_demo()
        
        if demo_ok:
            print("\n🎉 Setup and demo completed successfully!")
            print("\n📋 Next steps:")
            print("   1. Review and adjust config/drift_config.yaml")
            print("   2. Add devnet SOL to your wallet")
            print("   3. Run training: python src/drift_trainer.py train")
            print("   4. For live trading: python src/drift_trainer.py live")
        else:
            print("\n⚠️  Demo failed, but core components work")
    else:
        print("\n⚠️  Some tests failed. Please check:")
        if not drift_ok:
            print("   - Drift connection (check .env file)")
        if not agent_ok:
            print("   - Agent initialization")
        if not env_ok:
            print("   - Environment setup")
    
    print("\n📝 Setup complete!")

if __name__ == "__main__":
    asyncio.run(main())