"""
Alert Manager - Controlador principal del sistema de alertas
Maneja múltiples canales y tipos de alertas
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Set
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum
import json

from .channels.base_channel import BaseChannel, AlertPriority
from .channels.email_channel import EmailChannel
from .channels.telegram_channel import TelegramChannel
from .channels.discord_channel import DiscordChannel
from .channels.sms_channel import SMSChannel
from .triggers.base_trigger import BaseTrigger
from .triggers.signal_trigger import SignalTrigger
from .triggers.price_trigger import PriceTrigger
from .triggers.risk_trigger import RiskTrigger

logger = logging.getLogger(__name__)

@dataclass
class Alert:
    """Estructura de una alerta"""
    id: str
    title: str
    message: str
    priority: AlertPriority
    symbol: str
    timestamp: datetime
    channels: List[str]
    metadata: Dict[str, Any] = None
    sent: bool = False
    retry_count: int = 0

class AlertManager:
    """
    Gestor central del sistema de alertas
    Maneja triggers, canales y envío de notificaciones
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.channels: Dict[str, BaseChannel] = {}
        self.triggers: Dict[str, BaseTrigger] = {}
        
        # Queue de alertas pendientes
        self.alert_queue = asyncio.Queue()
        
        # Historial de alertas
        self.alert_history: List[Alert] = []
        
        # Rate limiting
        self.rate_limits = config.get('rate_limits', {})
        self.sent_alerts_tracker = {}
        
        # Control de duplicados
        self.duplicate_window = timedelta(
            minutes=config.get('duplicate_window_minutes', 5)
        )
        self.recent_alerts: Set[str] = set()
        
        # Workers para procesar alertas
        self.workers_running = False
        self.worker_tasks = []
        
        # Inicializar componentes
        self._init_channels()
        self._init_triggers()
    
    def _init_channels(self):
        """Inicializa canales de notificación"""
        channels_config = self.config.get('channels', {})
        
        for channel_name, channel_config in channels_config.items():
            if not channel_config.get('enabled', False):
                continue
            
            try:
                channel = self._create_channel(channel_name, channel_config)
                if channel:
                    self.channels[channel_name] = channel
                    logger.info(f"Canal {channel_name} inicializado")
                    
            except Exception as e:
                logger.error(f"Error inicializando canal {channel_name}: {e}")
    
    def _create_channel(self, name: str, config: Dict[str, Any]) -> Optional[BaseChannel]:
        """Factory para crear canales"""
        channel_type = config.get('type', '').lower()
        
        channel_map = {
            'email': EmailChannel,
            'telegram': TelegramChannel,
            'discord': DiscordChannel,
            'sms': SMSChannel,
        }
        
        if channel_type in channel_map:
            return channel_map[channel_type](config)
        else:
            logger.warning(f"Tipo de canal desconocido: {channel_type}")
            return None
    
    def _init_triggers(self):
        """Inicializa triggers de alertas"""
        triggers_config = self.config.get('triggers', {})
        
        for trigger_name, trigger_config in triggers_config.items():
            if not trigger_config.get('enabled', False):
                continue
            
            try:
                trigger = self._create_trigger(trigger_name, trigger_config)
                if trigger:
                    self.triggers[trigger_name] = trigger
                    logger.info(f"Trigger {trigger_name} inicializado")
                    
            except Exception as e:
                logger.error(f"Error inicializando trigger {trigger_name}: {e}")
    
    def _create_trigger(self, name: str, config: Dict[str, Any]) -> Optional[BaseTrigger]:
        """Factory para crear triggers"""
        trigger_type = config.get('type', '').lower()
        
        trigger_map = {
            'signal': SignalTrigger,
            'price': PriceTrigger,
            'risk': RiskTrigger,
        }
        
        if trigger_type in trigger_map:
            return trigger_map[trigger_type](config)
        else:
            logger.warning(f"Tipo de trigger desconocido: {trigger_type}")
            return None
    
    async def start(self):
        """Inicia el sistema de alertas"""
        if self.workers_running:
            return
        
        self.workers_running = True
        
        # Inicializar canales
        for channel in self.channels.values():
            await channel.initialize()
        
        # Crear workers para procesar alertas
        num_workers = self.config.get('alert_workers', 3)
        for i in range(num_workers):
            task = asyncio.create_task(self._alert_worker(f"worker-{i}"))
            self.worker_tasks.append(task)
        
        logger.info(f"AlertManager iniciado con {num_workers} workers")
    
    async def stop(self):
        """Detiene el sistema de alertas"""
        if not self.workers_running:
            return
        
        self.workers_running = False
        
        # Cancelar workers
        for task in self.worker_tasks:
            task.cancel()
        
        # Esperar que terminen
        await asyncio.gather(*self.worker_tasks, return_exceptions=True)
        self.worker_tasks.clear()
        
        # Cerrar canales
        for channel in self.channels.values():
            await channel.cleanup()
        
        logger.info("AlertManager detenido")
    
    async def _alert_worker(self, worker_name: str):
        """Worker que procesa alertas de la queue"""
        logger.info(f"Alert worker {worker_name} iniciado")
        
        while self.workers_running:
            try:
                # Obtener alerta de la queue con timeout
                alert = await asyncio.wait_for(
                    self.alert_queue.get(), 
                    timeout=1.0
                )
                
                await self._process_alert(alert)
                self.alert_queue.task_done()
                
            except asyncio.TimeoutError:
                # Timeout normal, continuar
                continue
            except Exception as e:
                logger.error(f"Error en worker {worker_name}: {e}")
        
        logger.info(f"Alert worker {worker_name} detenido")
    
    async def _process_alert(self, alert: Alert):
        """Procesa una alerta individual"""
        try:
            # Verificar rate limiting
            if not self._check_rate_limit(alert):
                logger.debug(f"Alerta {alert.id} bloqueada por rate limiting")
                return
            
            # Verificar duplicados
            if self._is_duplicate(alert):
                logger.debug(f"Alerta {alert.id} ignorada (duplicado)")
                return
            
            # Enviar por todos los canales especificados
            send_tasks = []
            for channel_name in alert.channels:
                if channel_name in self.channels:
                    channel = self.channels[channel_name]
                    task = channel.send_alert(alert)
                    send_tasks.append((channel_name, task))
            
            # Ejecutar envíos en paralelo
            for channel_name, task in send_tasks:
                try:
                    await task
                    logger.info(f"Alerta {alert.id} enviada por {channel_name}")
                except Exception as e:
                    logger.error(f"Error enviando alerta por {channel_name}: {e}")
                    
                    # Retry para alertas críticas
                    if alert.priority == AlertPriority.CRITICAL and alert.retry_count < 3:
                        alert.retry_count += 1
                        await asyncio.sleep(2 ** alert.retry_count)  # Backoff exponencial
                        await self.alert_queue.put(alert)
            
            # Marcar como enviada
            alert.sent = True
            self._track_sent_alert(alert)
            
            # Agregar a historial
            self.alert_history.append(alert)
            
            # Limpiar historial viejo
            self._cleanup_history()
            
        except Exception as e:
            logger.error(f"Error procesando alerta {alert.id}: {e}")
    
    def _check_rate_limit(self, alert: Alert) -> bool:
        """Verifica rate limiting por canal y prioridad"""
        now = datetime.now()
        
        for channel_name in alert.channels:
            # Obtener límites para este canal
            channel_limits = self.rate_limits.get(channel_name, {})
            priority_limit = channel_limits.get(alert.priority.value, {})
            
            max_per_hour = priority_limit.get('max_per_hour')
            max_per_minute = priority_limit.get('max_per_minute')
            
            if not max_per_hour and not max_per_minute:
                continue
            
            # Inicializar tracker si no existe
            key = f"{channel_name}_{alert.priority.value}"
            if key not in self.sent_alerts_tracker:
                self.sent_alerts_tracker[key] = []
            
            tracker = self.sent_alerts_tracker[key]
            
            # Limpiar alertas viejas
            hour_ago = now - timedelta(hours=1)
            minute_ago = now - timedelta(minutes=1)
            
            tracker[:] = [ts for ts in tracker if ts > hour_ago]
            
            # Verificar límites
            if max_per_hour:
                alerts_last_hour = len(tracker)
                if alerts_last_hour >= max_per_hour:
                    return False
            
            if max_per_minute:
                alerts_last_minute = len([ts for ts in tracker if ts > minute_ago])
                if alerts_last_minute >= max_per_minute:
                    return False
        
        return True
    
    def _track_sent_alert(self, alert: Alert):
        """Registra alerta enviada para rate limiting"""
        now = datetime.now()
        
        for channel_name in alert.channels:
            key = f"{channel_name}_{alert.priority.value}"
            if key not in self.sent_alerts_tracker:
                self.sent_alerts_tracker[key] = []
            
            self.sent_alerts_tracker[key].append(now)
    
    def _is_duplicate(self, alert: Alert) -> bool:
        """Verifica si la alerta es duplicada reciente"""
        # Crear hash único de la alerta
        alert_hash = f"{alert.symbol}_{alert.title}_{alert.message}"
        
        # Limpiar alertas viejas del set
        current_time = datetime.now()
        cutoff_time = current_time - self.duplicate_window
        
        # Filtrar alertas recientes
        recent_to_keep = set()
        for recent_hash in self.recent_alerts:
            # Aquí necesitaríamos más información para filtrar por tiempo
            # Por simplicidad, mantenemos todas por ahora
            recent_to_keep.add(recent_hash)
        
        self.recent_alerts = recent_to_keep
        
        # Verificar si es duplicado
        if alert_hash in self.recent_alerts:
            return True
        
        # Agregar a recientes
        self.recent_alerts.add(alert_hash)
        return False
    
    def _cleanup_history(self):
        """Limpia historial viejo de alertas"""
        max_history = self.config.get('max_history_size', 1000)
        
        if len(self.alert_history) > max_history:
            # Mantener solo las más recientes
            self.alert_history = self.alert_history[-max_history:]
    
    async def create_alert(
        self,
        title: str,
        message: str,
        symbol: str,
        priority: AlertPriority = AlertPriority.MEDIUM,
        channels: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Crea y encola una nueva alerta
        
        Returns:
            ID de la alerta creada
        """
        if channels is None:
            # Usar canales por defecto según prioridad
            default_channels = self.config.get('default_channels', {})
            channels = default_channels.get(priority.value, list(self.channels.keys()))
        
        # Filtrar canales disponibles
        available_channels = [ch for ch in channels if ch in self.channels]
        
        if not available_channels:
            logger.warning(f"No hay canales disponibles para alerta: {title}")
            return None
        
        # Crear alerta
        alert_id = f"alert_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hash(title) % 10000}"
        
        alert = Alert(
            id=alert_id,
            title=title,
            message=message,
            priority=priority,
            symbol=symbol,
            timestamp=datetime.now(),
            channels=available_channels,
            metadata=metadata or {}
        )
        
        # Encolar para procesamiento
        await self.alert_queue.put(alert)
        
        logger.info(f"Alerta creada: {alert_id} - {title}")
        return alert_id
    
    async def check_triggers(self, market_data: Dict[str, Any]):
        """
        Verifica todos los triggers con datos de mercado
        
        Args:
            market_data: Datos de mercado actuales
        """
        for trigger_name, trigger in self.triggers.items():
            try:
                should_trigger, alert_data = await trigger.check(market_data)
                
                if should_trigger:
                    await self.create_alert(**alert_data)
                    
            except Exception as e:
                logger.error(f"Error verificando trigger {trigger_name}: {e}")
    
    def get_alert_stats(self) -> Dict[str, Any]:
        """Obtiene estadísticas del sistema de alertas"""
        now = datetime.now()
        last_hour = now - timedelta(hours=1)
        last_24h = now - timedelta(hours=24)
        
        # Filtrar alertas por tiempo
        alerts_last_hour = [a for a in self.alert_history if a.timestamp > last_hour]
        alerts_last_24h = [a for a in self.alert_history if a.timestamp > last_24h]
        
        return {
            'total_alerts_sent': len(self.alert_history),
            'alerts_last_hour': len(alerts_last_hour),
            'alerts_last_24h': len(alerts_last_24h),
            'pending_alerts': self.alert_queue.qsize(),
            'active_channels': len(self.channels),
            'active_triggers': len(self.triggers),
            'workers_running': self.workers_running,
            'duplicate_window_minutes': self.duplicate_window.total_seconds() / 60,
            'channel_status': {
                name: channel.get_status() 
                for name, channel in self.channels.items()
            }
        }