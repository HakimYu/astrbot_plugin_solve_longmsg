from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import Node, Plain


@register("revoke-long-msg", "HakimYu", "检测并处理长消息", "1.0.0")
class LongMessageHandler(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.max_length = 100  # 设置最大消息长度

    async def initialize(self):
        """插件初始化方法"""
        pass

    @filter.message(filter.EventMessageType.GROUP_MESSAGE)
    async def handle_message(self, event: AstrMessageEvent):
        """处理所有消息，检测长度并处理"""
        message_str = event.message_str
        if len(message_str) > self.max_length:
            # 获取发送者信息
            sender_name = event.get_sender_name()
            sender_id = event.get_sender_id()

            # 创建合并转发节点
            node = Node(
                uin=sender_id,
                name=sender_name,
                content=[Plain(message_str)]
            )

            # 撤回原消息
            await event.revoke()

            # 发送合并转发消息
            yield event.chain_result([node])
