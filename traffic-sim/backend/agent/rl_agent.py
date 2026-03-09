
import torch
import torch.nn as nn

# DQN-style traffic RL agent
class TrafficRLAgent(nn.Module):
	def __init__(self):
		super().__init__()
		# Input: 12 features, Output: 4 Q-values
		self.fc1 = nn.Linear(12, 64)
		self.relu1 = nn.ReLU()
		self.fc2 = nn.Linear(64, 64)
		self.relu2 = nn.ReLU()
		self.fc3 = nn.Linear(64, 4)

	def forward(self, x):
		x = self.fc1(x)
		x = self.relu1(x)
		x = self.fc2(x)
		x = self.relu2(x)
		x = self.fc3(x)
		return x
