from astrbot.api.event import filter, AstrMessageEvent, MessageChain
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
from astrbot.api.message_components import Node, Plain, Nodes
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent


@register("solve_longmsg", "HakimYu", "检测并处理长消息", "1.0.2")
class LongMessageHandler(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config


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
                try:
                    await client.delete_msg(message_id=int(event.message_obj.message_id))
                except Exception as e:
                    logger.info(f"消息撤回失败: {e}，可能已被手动撤回，取消转发。")
                    return

                # 发送合并转发消息
                node = Node(
                    uin=sender_id,
                    name=sender_name,
                    content=[Plain(message_str)]
                )
                await event.send(event.chain_result([node]))
                event.stop_event()