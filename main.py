from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
from astrbot.api.message_components import Node
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent


@register("solve_longmsg", "HakimYu", "撤回并合并转发群员或者机器人的长消息", "1.1.1")
class LongMessageHandler(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.message_chain = None

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def handle_message(self, event: AstrMessageEvent):
        """处理所有消息，检测长度并处理"""
        if not self.config.solve_group_member:
            return
        group_id = event.get_group_id()
        if self.config.group_whitelist and group_id not in self.config.group_whitelist:
            return

        message_str = event.message_str
        if len(message_str) > self.config.max_length:
            # 撤回原消息
            if event.get_platform_name() == "aiocqhttp":
                assert isinstance(event, AiocqhttpMessageEvent)
                client = event.bot
                try:
                    await client.delete_msg(message_id=int(event.message_obj.message_id))
                except Exception as e:
                    logger.info(f"消息撤回失败: {e}，可能已被手动撤回，取消转发。")

                # 储存消息链
                self.message_chain = MessageChain([Node(
                    uin=event.get_sender_id(),
                    name=event.get_sender_name(),
                    content=event.get_messages()
                )])

    @filter.on_decorating_result()
    async def on_decorating_result(self, event: AstrMessageEvent):
        if self.message_chain:
            await event.send(self.message_chain)
            self.message_chain = None
        result = event.get_result()
        chain = result.chain
        if not self.config.solve_self_message:
            return
        if len(result.get_plain_text()) > self.config.max_length:
            await event.send(MessageChain([Node(
                uin=event.get_self_id(),
                name="",
                content=chain
            )]))
            chain.clear()