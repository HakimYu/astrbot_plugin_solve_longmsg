from astrbot.api.event import filter, AstrMessageEvent, MessageChain
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
from astrbot.api.message_components import Node, Plain, Nodes
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent


@register("solve_longmsg", "HakimYu", "检测并处理长消息", "1.0.1")
class LongMessageHandler(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config

    def _create_forward_node(self, user_id: str, nickname: str, content: str) -> dict:
        """创建转发节点"""
        return {
            "type": "node",
            "data": {
                "user_id": user_id,
                "nickname": nickname,
                "content": [{"type": "text", "data": {"text": content}}]
            }
        }

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def handle_message(self, event: AstrMessageEvent):
        """处理所有消息，检测长度并处理"""
        group_id = event.get_group_id()
        if self.config.group_whitelist and group_id not in self.config.group_whitelist:
            return

        message_str = event.message_str
        if len(message_str) > self.config.max_length:
            # 获取发送者信息
            sender_name = event.get_sender_name()
            sender_id = event.get_sender_id()
            
            # 撤回原消息
            if event.get_platform_name() == "aiocqhttp":
                assert isinstance(event, AiocqhttpMessageEvent)
                client = event.bot
                payloads = {
                    "message_id": event.message_obj.message_id,
                }
                ret = await client.api.call_action('delete_msg', **payloads)
                logger.info(f"delete_msg: {ret}")

                # 发送合并转发消息
                node = self._create_forward_node(str(sender_id), sender_name, message_str)
                forward_payloads = {
                    "group_id": group_id,
                    "messages": [node]
                }
                ret = await client.api.call_action('send_group_forward_msg', **forward_payloads)
                return