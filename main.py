from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
from astrbot.api.message_components import Node, Plain
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
from typing import Optional, Union
import asyncio


@register("revoke-long-msg", "HakimYu", "检测并处理长消息", "1.0.0")
class LongMessageHandler(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self._validate_config()
        if self._should_log():
            logger.info(f"LongMessageHandler initialized with max_length={self.config.max_length}, "
                       f"group_whitelist={self.config.group_whitelist}")

    def _should_log(self) -> bool:
        """检查是否应该记录日志"""
        return getattr(self.config, 'enable_logging', True)

    def _validate_config(self) -> None:
        """验证配置参数的有效性"""
        try:
            # 验证 max_length
            if not isinstance(self.config.max_length, int) or self.config.max_length <= 0:
                if self._should_log():
                    logger.warning(f"Invalid max_length: {self.config.max_length}, using default value 100")
                self.config.max_length = 100
            
            # 验证 group_whitelist
            if not isinstance(self.config.group_whitelist, list):
                if self._should_log():
                    logger.warning(f"Invalid group_whitelist: {self.config.group_whitelist}, using empty list")
                self.config.group_whitelist = []
            
            # 确保白名单中的群号都是有效的整数
            valid_group_ids = []
            for group_id in self.config.group_whitelist:
                try:
                    valid_group_ids.append(int(group_id))
                except (ValueError, TypeError):
                    if self._should_log():
                        logger.warning(f"Invalid group_id in whitelist: {group_id}")
            
            self.config.group_whitelist = valid_group_ids
            
            # 验证其他配置项
            if not hasattr(self.config, 'enable_fallback'):
                self.config.enable_fallback = True
            
            if not hasattr(self.config, 'fallback_preview_length'):
                self.config.fallback_preview_length = 100
            elif not isinstance(self.config.fallback_preview_length, int) or self.config.fallback_preview_length < 10:
                self.config.fallback_preview_length = 100
            
            if not hasattr(self.config, 'retry_count'):
                self.config.retry_count = 2
            elif not isinstance(self.config.retry_count, int) or self.config.retry_count < 0:
                self.config.retry_count = 2
            
            if not hasattr(self.config, 'retry_delay'):
                self.config.retry_delay = 1.0
            elif not isinstance(self.config.retry_delay, (int, float)) or self.config.retry_delay < 0.1:
                self.config.retry_delay = 1.0
            
        except Exception as e:
            logger.error(f"Error validating config: {e}")
            # 使用默认配置
            self.config.max_length = 100
            self.config.group_whitelist = []
            self.config.enable_fallback = True
            self.config.fallback_preview_length = 100
            self.config.retry_count = 2
            self.config.retry_delay = 1.0

    def _should_process_group(self, group_id: Optional[Union[int, str]]) -> bool:
        """检查是否应该处理该群的消息"""
        try:
            if group_id is None:
                return False
            
            group_id = int(group_id)
            
            # 如果白名单为空，处理所有群
            if not self.config.group_whitelist:
                return True
            
            return group_id in self.config.group_whitelist
            
        except (ValueError, TypeError) as e:
            if self._should_log():
                logger.warning(f"Invalid group_id format: {group_id}, error: {e}")
            return False

    def _get_sender_info(self, event: AstrMessageEvent) -> tuple[str, Union[int, str]]:
        """安全地获取发送者信息"""
        try:
            sender_name = event.get_sender_name() or "未知用户"
            sender_id = event.get_sender_id() or 0
            return sender_name, sender_id
        except Exception as e:
            if self._should_log():
                logger.error(f"Error getting sender info: {e}")
            return "未知用户", 0

    async def _revoke_message_with_retry(self, event: AstrMessageEvent) -> bool:
        """带重试机制的消息撤回"""
        for attempt in range(self.config.retry_count + 1):
            try:
                if event.get_platform_name() == "aiocqhttp":
                    assert isinstance(event, AiocqhttpMessageEvent)
                    client = event.bot
                    
                    # 检查消息对象和消息ID是否存在
                    if not hasattr(event, 'message_obj') or not hasattr(event.message_obj, 'message_id'):
                        if self._should_log():
                            logger.warning("Message object or message_id not available")
                        return False
                    
                    payloads = {
                        "message_id": event.message_obj.message_id,
                    }
                    
                    ret = await client.api.call_action('delete_msg', **payloads)
                    if self._should_log():
                        logger.info(f"Message revoked successfully: {ret}")
                    return True
                else:
                    if self._should_log():
                        logger.warning(f"Unsupported platform: {event.get_platform_name()}")
                    return False
                    
            except Exception as e:
                if attempt < self.config.retry_count:
                    if self._should_log():
                        logger.warning(f"Revoke attempt {attempt + 1} failed: {e}, retrying...")
                    await asyncio.sleep(self.config.retry_delay)
                else:
                    if self._should_log():
                        logger.error(f"All revoke attempts failed: {e}")
                    return False
        
        return False

    async def _create_forward_node(self, message_str: str, sender_name: str, sender_id: Union[int, str]) -> Optional[Node]:
        """安全地创建合并转发节点"""
        try:
            node = Node(
                uin=sender_id,
                name=sender_name,
                content=[Plain(message_str)]
            )
            return node
        except Exception as e:
            if self._should_log():
                logger.error(f"Error creating forward node: {e}")
            return None

    async def _send_fallback_message(self, event: AstrMessageEvent, message_str: str, sender_name: str) -> None:
        """发送备选消息（当合并转发失败时）"""
        if not self.config.enable_fallback:
            return
            
        try:
            # 截取消息前指定长度的字符作为预览
            preview_length = self.config.fallback_preview_length
            preview = message_str[:preview_length] + "..." if len(message_str) > preview_length else message_str
            fallback_text = f"来自 {sender_name} 的长消息（已撤回原消息）：\n{preview}"
            
            fallback_node = Node(
                uin=0,  # 使用机器人ID
                name="系统",
                content=[Plain(fallback_text)]
            )
            
            yield event.chain_result([fallback_node])
            if self._should_log():
                logger.info("Sent fallback message")
            
        except Exception as e:
            if self._should_log():
                logger.error(f"Error sending fallback message: {e}")

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def handle_message(self, event: AstrMessageEvent):
        """处理所有消息，检测长度并处理"""
        try:
            # 获取群号并检查是否应该处理
            group_id = event.get_group_id()
            if not self._should_process_group(group_id):
                return

            # 获取消息内容
            message_str = event.message_str
            if not message_str:
                if self._should_log():
                    logger.debug("Empty message received, skipping")
                return

            # 检查消息长度
            if len(message_str) <= self.config.max_length:
                return

            if self._should_log():
                logger.info(f"Long message detected in group {group_id}, length: {len(message_str)}")

            # 获取发送者信息
            sender_name, sender_id = self._get_sender_info(event)

            # 尝试撤回原消息
            revoke_success = await self._revoke_message_with_retry(event)
            if not revoke_success and self._should_log():
                logger.warning("Failed to revoke original message, but continuing with forward")

            # 创建合并转发节点
            node = await self._create_forward_node(message_str, sender_name, sender_id)
            if node is None:
                return

            # 发送合并转发消息
            try:
                yield event.chain_result([node])
                if self._should_log():
                    logger.info(f"Successfully processed long message from {sender_name} in group {group_id}")
            except Exception as e:
                if self._should_log():
                    logger.error(f"Error sending forward message: {e}")
                # 如果转发失败且撤回成功，可以考虑发送普通消息作为备选方案
                if revoke_success:
                    await self._send_fallback_message(event, message_str, sender_name)

        except Exception as e:
            logger.error(f"Unexpected error in handle_message: {e}", exc_info=True)

    async def on_enable(self):
        """插件启用时的处理"""
        try:
            if self._should_log():
                logger.info("LongMessageHandler plugin enabled")
            self._validate_config()
        except Exception as e:
            logger.error(f"Error during plugin enable: {e}")

    async def on_disable(self):
        """插件禁用时的处理"""
        try:
            if self._should_log():
                logger.info("LongMessageHandler plugin disabled")
        except Exception as e:
            logger.error(f"Error during plugin disable: {e}")
