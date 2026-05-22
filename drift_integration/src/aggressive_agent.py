"""
Aggressive DQN Agent optimized for high returns (900% target)
Enhanced version of the original Agent with advanced features
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import numpy as np
import random
from collections import deque, namedtuple
import logging
from typing import Dict, List, Tuple, Optional
import yaml

# Import original components
import sys
import os
sys.path.append('../repos/repos/Trading-Bot---Deep-Reinforcement-Learning/Bot_code_and_models')
from utils import ReplayMemory, Transition

class NoisyLinear(nn.Module):
    """Noisy Linear Layer for better exploration"""
    
    def __init__(self, in_features: int, out_features: int, std_init: float = 0.5):
        super(NoisyLinear, self).__init__()
        self.in_features = in_features
        self.out_features = out_features
        self.std_init = std_init
        
        self.weight_mu = nn.Parameter(torch.empty(out_features, in_features))
        self.weight_sigma = nn.Parameter(torch.empty(out_features, in_features))
        self.register_buffer('weight_epsilon', torch.empty(out_features, in_features))
        
        self.bias_mu = nn.Parameter(torch.empty(out_features))
        self.bias_sigma = nn.Parameter(torch.empty(out_features))
        self.register_buffer('bias_epsilon', torch.empty(out_features))
        
        self.reset_parameters()
        self.reset_noise()
    
    def reset_parameters(self):
        mu_range = 1 / np.sqrt(self.in_features)
        self.weight_mu.data.uniform_(-mu_range, mu_range)
        self.weight_sigma.data.fill_(self.std_init / np.sqrt(self.in_features))
        self.bias_mu.data.uniform_(-mu_range, mu_range)
        self.bias_sigma.data.fill_(self.std_init / np.sqrt(self.out_features))
    
    def reset_noise(self):
        epsilon_in = self._scale_noise(self.in_features)
        epsilon_out = self._scale_noise(self.out_features)
        self.weight_epsilon.copy_(epsilon_out.ger(epsilon_in))
        self.bias_epsilon.copy_(epsilon_out)
    
    def _scale_noise(self, size: int) -> torch.Tensor:
        x = torch.randn(size)
        return x.sign().mul_(x.abs().sqrt_())
    
    def forward(self, input: torch.Tensor) -> torch.Tensor:
        if self.training:
            return F.linear(input, self.weight_mu + self.weight_sigma * self.weight_epsilon,
                          self.bias_mu + self.bias_sigma * self.bias_epsilon)
        else:
            return F.linear(input, self.weight_mu, self.bias_mu)

class AggressiveDQN(nn.Module):
    """
    Enhanced DQN architecture for aggressive trading
    Features: Dueling Networks, Noisy Networks, Attention Mechanism
    """
    
    def __init__(self, 
                 input_dim: int = 32,
                 hidden_dims: List[int] = [256, 512, 256],
                 output_dim: int = 3,
                 use_noisy: bool = True,
                 use_attention: bool = True,
                 dropout_rate: float = 0.2):
        super(AggressiveDQN, self).__init__()
        
        self.input_dim = input_dim
        self.hidden_dims = hidden_dims
        self.output_dim = output_dim
        self.use_noisy = use_noisy
        self.use_attention = use_attention
        
        # Input normalization
        self.input_norm = nn.LayerNorm(input_dim)
        
        # Feature extraction layers
        self.feature_layers = nn.ModuleList()
        prev_dim = input_dim
        
        for hidden_dim in hidden_dims:
            if use_noisy:
                self.feature_layers.append(NoisyLinear(prev_dim, hidden_dim))
            else:
                self.feature_layers.append(nn.Linear(prev_dim, hidden_dim))
            self.feature_layers.append(nn.LayerNorm(hidden_dim))
            self.feature_layers.append(nn.ReLU())
            self.feature_layers.append(nn.Dropout(dropout_rate))
            prev_dim = hidden_dim
        
        # Attention mechanism for feature importance
        if use_attention:
            self.attention = nn.MultiheadAttention(
                embed_dim=hidden_dims[-1],
                num_heads=8,
                dropout=dropout_rate,
                batch_first=True
            )
        
        # Dueling architecture
        final_dim = hidden_dims[-1]
        
        # Value stream
        if use_noisy:
            self.value_stream = nn.Sequential(
                NoisyLinear(final_dim, final_dim // 2),
                nn.ReLU(),
                NoisyLinear(final_dim // 2, 1)
            )
        else:
            self.value_stream = nn.Sequential(
                nn.Linear(final_dim, final_dim // 2),
                nn.ReLU(),
                nn.Linear(final_dim // 2, 1)
            )
        
        # Advantage stream
        if use_noisy:
            self.advantage_stream = nn.Sequential(
                NoisyLinear(final_dim, final_dim // 2),
                nn.ReLU(),
                NoisyLinear(final_dim // 2, output_dim)
            )
        else:
            self.advantage_stream = nn.Sequential(
                nn.Linear(final_dim, final_dim // 2),
                nn.ReLU(),
                nn.Linear(final_dim // 2, output_dim)
            )
        
        # Market regime classifier (auxiliary task)
        self.regime_classifier = nn.Sequential(
            nn.Linear(final_dim, 64),
            nn.ReLU(),
            nn.Linear(64, 3)  # Bull, Bear, Sideways
        )
    
    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        # Normalize input
        x = self.input_norm(x)
        
        # Feature extraction
        features = x
        for layer in self.feature_layers:
            if isinstance(layer, (nn.Linear, NoisyLinear)):
                features = layer(features)
            else:
                features = layer(features)
        
        # Apply attention if enabled
        if self.use_attention:
            # Reshape for attention (add sequence dimension)
            features_seq = features.unsqueeze(1)
            attended_features, _ = self.attention(features_seq, features_seq, features_seq)
            features = attended_features.squeeze(1)
        
        # Dueling streams
        value = self.value_stream(features)
        advantage = self.advantage_stream(features)
        
        # Combine value and advantage
        q_values = value + (advantage - advantage.mean(dim=1, keepdim=True))
        
        # Market regime prediction (auxiliary)
        regime_pred = self.regime_classifier(features)
        
        return q_values, regime_pred
    
    def reset_noise(self):
        """Reset noise in noisy layers"""
        if self.use_noisy:
            for layer in self.modules():
                if isinstance(layer, NoisyLinear):
                    layer.reset_noise()

class PrioritizedReplayBuffer:
    """
    Prioritized Experience Replay Buffer
    """
    
    def __init__(self, capacity: int, alpha: float = 0.6, beta: float = 0.4):
        self.capacity = capacity
        self.alpha = alpha
        self.beta = beta
        self.beta_increment = 0.001
        
        self.buffer = []
        self.priorities = np.zeros((capacity,), dtype=np.float32)
        self.position = 0
        self.size = 0
    
    def add(self, state, action, reward, next_state, done):
        """Add experience to buffer"""
        max_priority = self.priorities.max() if self.buffer else 1.0
        
        if len(self.buffer) < self.capacity:
            self.buffer.append(None)
        
        self.buffer[self.position] = Transition(state, action, next_state, reward)
        self.priorities[self.position] = max_priority
        
        self.position = (self.position + 1) % self.capacity
        self.size = min(self.size + 1, self.capacity)
    
    def sample(self, batch_size: int) -> Tuple[List, np.ndarray, np.ndarray]:
        """Sample batch with priorities"""
        if self.size == 0:
            return [], np.array([]), np.array([])
        
        priorities = self.priorities[:self.size]
        probabilities = priorities ** self.alpha
        probabilities /= probabilities.sum()
        
        indices = np.random.choice(self.size, batch_size, p=probabilities)
        
        # Importance sampling weights
        weights = (self.size * probabilities[indices]) ** (-self.beta)
        weights /= weights.max()
        
        batch = [self.buffer[idx] for idx in indices]
        
        return batch, indices, weights
    
    def update_priorities(self, indices: np.ndarray, errors: np.ndarray):
        """Update priorities based on TD errors"""
        for idx, error in zip(indices, errors):
            self.priorities[idx] = abs(error) + 1e-6  # Small epsilon to avoid zero priority
    
    def increment_beta(self):
        """Increment beta towards 1.0"""
        self.beta = min(1.0, self.beta + self.beta_increment)

class AggressiveAgent:
    """
    Aggressive DQN Agent for high-return trading
    """
    
    def __init__(self, config_path: str = "config/drift_config.yaml"):
        self.config = self._load_config(config_path)
        self.logger = self._setup_logging()
        
        # Model configuration
        model_config = self.config['model']
        self.input_dim = model_config['input_features']
        self.hidden_dims = model_config['hidden_layers']
        self.lr = model_config['learning_rate']
        self.batch_size = model_config['batch_size']
        self.memory_size = model_config['memory_size']
        self.target_update = model_config['target_update_freq']
        self.gamma = model_config['gamma']
        
        # Exploration parameters
        self.epsilon = model_config['epsilon_start']
        self.epsilon_end = model_config['epsilon_end']
        self.epsilon_decay = model_config['epsilon_decay']
        
        # Advanced features
        self.use_prioritized_replay = model_config['prioritized_replay']
        self.use_double_dqn = model_config['double_dqn']
        self.use_dueling = model_config['dueling_networks']
        self.use_noisy = model_config['noisy_networks']
        self.n_step = model_config['multi_step_learning']
        
        # Device selection
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.logger.info(f"Using device: {self.device}")
        
        # Initialize networks
        self.q_network = AggressiveDQN(
            input_dim=self.input_dim,
            hidden_dims=self.hidden_dims,
            use_noisy=self.use_noisy
        ).to(self.device)
        
        self.target_network = AggressiveDQN(
            input_dim=self.input_dim,
            hidden_dims=self.hidden_dims,
            use_noisy=self.use_noisy
        ).to(self.device)
        
        # Copy weights to target network
        self.target_network.load_state_dict(self.q_network.state_dict())
        self.target_network.eval()
        
        # Optimizer
        self.optimizer = optim.AdamW(
            self.q_network.parameters(),
            lr=self.lr,
            weight_decay=1e-5
        )
        
        # Learning rate scheduler
        self.scheduler = optim.lr_scheduler.ReduceLROnPlateau(
            self.optimizer, 
            mode='max', 
            factor=0.5, 
            patience=100,
            verbose=True
        )
        
        # Experience replay
        if self.use_prioritized_replay:
            self.memory = PrioritizedReplayBuffer(self.memory_size)
        else:
            self.memory = ReplayMemory(self.memory_size)
        
        # N-step learning buffer
        self.n_step_buffer = deque(maxlen=self.n_step)
        
        # Training metrics
        self.steps_done = 0
        self.episode_rewards = []
        self.losses = []
        self.q_values = []
        
        # Performance tracking
        self.best_performance = -float('inf')
        self.performance_history = []
        
        self.logger.info("✅ AggressiveAgent initialized")
    
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
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        return logging.getLogger(__name__)
    
    def select_action(self, state: np.ndarray, training: bool = True) -> int:
        """
        Select action using epsilon-greedy with noisy networks
        """
        self.steps_done += 1
        
        # Convert state to tensor
        state_tensor = torch.FloatTensor(state).unsqueeze(0).to(self.device)
        
        # Epsilon-greedy (reduced importance with noisy networks)
        if training and not self.use_noisy and random.random() < self.epsilon:
            action = random.randrange(3)
        else:
            with torch.no_grad():
                self.q_network.eval()
                q_values, _ = self.q_network(state_tensor)
                action = q_values.max(1)[1].item()
                
                # Track Q-values for monitoring
                self.q_values.append(q_values.max().item())
        
        # Decay epsilon
        if training and self.epsilon > self.epsilon_end:
            self.epsilon *= self.epsilon_decay
        
        return action
    
    def get_action_confidence(self, state: np.ndarray) -> float:
        """
        Get confidence score for current action
        """
        state_tensor = torch.FloatTensor(state).unsqueeze(0).to(self.device)
        
        with torch.no_grad():
            self.q_network.eval()
            q_values, _ = self.q_network(state_tensor)
            
            # Calculate confidence as max Q-value normalized by Q-value range
            q_max = q_values.max().item()
            q_min = q_values.min().item()
            q_range = q_max - q_min
            
            if q_range > 0:
                confidence = (q_max - q_min) / q_range
            else:
                confidence = 0.5
            
            return confidence
    
    def store_transition(self, state, action, reward, next_state, done):
        """
        Store experience in replay buffer with N-step learning
        """
        # Add to N-step buffer
        self.n_step_buffer.append((state, action, reward, next_state, done))
        
        if len(self.n_step_buffer) == self.n_step:
            # Calculate N-step return
            n_step_reward = 0
            for i, (_, _, r, _, d) in enumerate(self.n_step_buffer):
                n_step_reward += (self.gamma ** i) * r
                if d:
                    break
            
            # Get first and last transitions
            first_transition = self.n_step_buffer[0]
            last_transition = self.n_step_buffer[-1]
            
            # Store in replay buffer
            if self.use_prioritized_replay:
                self.memory.add(
                    first_transition[0],  # state
                    first_transition[1],  # action
                    n_step_reward,        # n-step reward
                    last_transition[3],   # next_state
                    last_transition[4]    # done
                )
            else:
                self.memory.push(
                    first_transition[0],
                    first_transition[1], 
                    last_transition[3],
                    n_step_reward
                )
    
    def train_step(self) -> float:
        """
        Perform one training step
        """
        if self.use_prioritized_replay:
            if self.memory.size < self.batch_size:
                return 0.0
            
            batch, indices, weights = self.memory.sample(self.batch_size)
            weights = torch.FloatTensor(weights).to(self.device)
        else:
            if len(self.memory) < self.batch_size:
                return 0.0
            
            transitions = self.memory.sample(self.batch_size)
            batch = Transition(*zip(*transitions))
            weights = torch.ones(self.batch_size).to(self.device)
        
        # Convert batch to tensors
        state_batch = torch.FloatTensor(np.array([t.state for t in batch])).to(self.device)
        action_batch = torch.LongTensor([t.action for t in batch]).to(self.device)
        reward_batch = torch.FloatTensor([t.reward for t in batch]).to(self.device)
        next_state_batch = torch.FloatTensor(np.array([t.next_state for t in batch])).to(self.device)
        
        # Current Q-values
        self.q_network.train()
        current_q_values, regime_pred = self.q_network(state_batch)
        current_q_values = current_q_values.gather(1, action_batch.unsqueeze(1))
        
        # Next Q-values
        with torch.no_grad():
            if self.use_double_dqn:
                # Double DQN: use online network for action selection, target for evaluation
                next_q_values_online, _ = self.q_network(next_state_batch)
                next_actions = next_q_values_online.max(1)[1].unsqueeze(1)
                
                next_q_values_target, _ = self.target_network(next_state_batch)
                next_q_values = next_q_values_target.gather(1, next_actions)
            else:
                # Standard DQN
                next_q_values, _ = self.target_network(next_state_batch)
                next_q_values = next_q_values.max(1)[0].unsqueeze(1)
        
        # Target Q-values
        target_q_values = reward_batch.unsqueeze(1) + (self.gamma ** self.n_step) * next_q_values
        
        # Calculate loss
        td_errors = target_q_values - current_q_values
        loss = (weights.unsqueeze(1) * td_errors.pow(2)).mean()
        
        # Auxiliary loss for market regime prediction (helps with feature learning)
        # Create dummy regime labels (could be enhanced with actual regime detection)
        regime_labels = torch.randint(0, 3, (state_batch.size(0),)).to(self.device)
        regime_loss = F.cross_entropy(regime_pred, regime_labels)
        
        total_loss = loss + 0.1 * regime_loss  # Weight auxiliary loss
        
        # Optimize
        self.optimizer.zero_grad()
        total_loss.backward()
        
        # Gradient clipping
        torch.nn.utils.clip_grad_norm_(self.q_network.parameters(), max_norm=1.0)
        
        self.optimizer.step()
        
        # Update priorities if using prioritized replay
        if self.use_prioritized_replay:
            td_errors_np = td_errors.detach().cpu().numpy().flatten()
            self.memory.update_priorities(indices, td_errors_np)
            self.memory.increment_beta()
        
        # Reset noise in noisy networks
        if self.use_noisy:
            self.q_network.reset_noise()
            self.target_network.reset_noise()
        
        # Track loss
        loss_value = total_loss.item()
        self.losses.append(loss_value)
        
        return loss_value
    
    def update_target_network(self):
        """Update target network"""
        self.target_network.load_state_dict(self.q_network.state_dict())
    
    def save_model(self, filepath: str, metadata: Dict = None):
        """Save model and training state"""
        save_dict = {
            'q_network_state_dict': self.q_network.state_dict(),
            'target_network_state_dict': self.target_network.state_dict(),
            'optimizer_state_dict': self.optimizer.state_dict(),
            'scheduler_state_dict': self.scheduler.state_dict(),
            'epsilon': self.epsilon,
            'steps_done': self.steps_done,
            'config': self.config,
            'performance_history': self.performance_history,
            'best_performance': self.best_performance
        }
        
        if metadata:
            save_dict.update(metadata)
        
        torch.save(save_dict, filepath)
        self.logger.info(f"Model saved to {filepath}")
    
    def load_model(self, filepath: str):
        """Load model and training state"""
        try:
            checkpoint = torch.load(filepath, map_location=self.device)
            
            self.q_network.load_state_dict(checkpoint['q_network_state_dict'])
            self.target_network.load_state_dict(checkpoint['target_network_state_dict'])
            self.optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
            self.scheduler.load_state_dict(checkpoint['scheduler_state_dict'])
            
            self.epsilon = checkpoint['epsilon']
            self.steps_done = checkpoint['steps_done']
            self.performance_history = checkpoint.get('performance_history', [])
            self.best_performance = checkpoint.get('best_performance', -float('inf'))
            
            self.logger.info(f"Model loaded from {filepath}")
            
        except Exception as e:
            self.logger.error(f"Failed to load model: {e}")
    
    def get_training_stats(self) -> Dict:
        """Get current training statistics"""
        return {
            'epsilon': self.epsilon,
            'steps_done': self.steps_done,
            'avg_q_value': np.mean(self.q_values[-100:]) if self.q_values else 0.0,
            'avg_loss': np.mean(self.losses[-100:]) if self.losses else 0.0,
            'memory_size': self.memory.size if hasattr(self.memory, 'size') else len(self.memory),
            'best_performance': self.best_performance,
            'current_lr': self.optimizer.param_groups[0]['lr']
        }

# Example usage
if __name__ == "__main__":
    # Test the aggressive agent
    agent = AggressiveAgent()
    
    # Test action selection
    dummy_state = np.random.randn(32)
    action = agent.select_action(dummy_state)
    confidence = agent.get_action_confidence(dummy_state)
    
    print(f"Selected action: {action}")
    print(f"Action confidence: {confidence:.3f}")
    print(f"Training stats: {agent.get_training_stats()}")