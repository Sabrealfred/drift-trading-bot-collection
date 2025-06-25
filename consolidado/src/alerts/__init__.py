"""
Alert System - Sistema de alertas multichannel
Integra notificaciones por email, SMS, Telegram, Discord, etc.
"""

from .alert_manager import AlertManager
from .channels import *
from .triggers import *
from .templates import *

__all__ = [
    'AlertManager',
    'EmailChannel',
    'TelegramChannel', 
    'DiscordChannel',
    'SMSChannel',
    'SignalTrigger',
    'PriceTrigger',
    'RiskTrigger'
]