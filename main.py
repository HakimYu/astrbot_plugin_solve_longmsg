from astrbot.api.event import filter, AstrMessageEvent, MessageChain
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
from astrbot.api.message_components import Node, Plain, Nodes
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional


class MessageContent(BaseModel):
    """消息内容模型"""
    model_config = ConfigDict(frozen=True)
    
    type: str = "text"
    data: dict = Field(default_factory=lambda: {"text": ""})


class ForwardNodeData(BaseModel):
    """合并转发节点数据模型"""
    model_config = ConfigDict(frozen=True)
    
    user_id: str
    nickname: str
    content: List[MessageContent]


class ForwardNode(BaseModel):
    """合并转发节点模型"""
    model_config = ConfigDict(frozen=True)
    
    type: str = "node"
    data: ForwardNodeData


class DeleteMessagePayload(BaseModel):
    """删除消息的载荷模型"""
    model_config = ConfigDict(frozen=True)
    
    message_id: int


class ForwardMessagePayload(BaseModel):
    """合并转发消息的载荷模型"""
    model_config = ConfigDict(frozen=True)
    
    group_id: int
    messages: List[ForwardNode]


class PluginConfig(BaseModel):
    """插件配置模型"""
    max_length: int = Field(default=100, description="触发合并转发的消息长度阈值")
    group_whitelist: List[int] = Field(default_factory=list, description="群白名单")


@register("revoke-long-msg", "HakimYu", "检测并处理长消息", "1.0.0")
class LongMessageHandler(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = PluginConfig(**config.dict())

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def handle_message(self, event: AstrMessageEvent):
        """处理所有消息，检测长度并处理"""
        group_id = event.get_group_id()
        if self.config.group_whitelist and group_id not in self.config.group_whitelist:
            return

        message_str = event.message_str
        if len(message_str) > self.config.max_length:
            await self._handle_long_message(event, group_id, message_str)

    async def _handle_long_message(self, event: AstrMessageEvent, group_id: int, message_str: str):
        """处理长消息：撤回原消息并发送合并转发"""
        if event.get_platform_name() != "aiocqhttp":
            return
            
        assert isinstance(event, AiocqhttpMessageEvent)
        client = event.bot
        
        # 获取发送者信息
        sender_name = event.get_sender_name()
        sender_id = event.get_sender_id()
        
        # 撤回原消息
        await self._delete_message(client, event.message_obj.message_id)
        
        # 发送合并转发消息
        await self._send_forward_message(client, group_id, sender_id, sender_name, message_str)

    async def _delete_message(self, client, message_id: int):
        """删除消息"""
        delete_payload = DeleteMessagePayload(message_id=message_id)
        ret = await client.api.call_action('delete_msg', **delete_payload.model_dump())
        logger.info(f"delete_msg: {ret}")

    async def _send_forward_message(self, client, group_id: int, sender_id: int, sender_name: str, message_str: str):
        """发送合并转发消息"""
        # 创建消息内容
        message_content = MessageContent(data={"text": message_str})
        
        # 创建转发节点数据
        node_data = ForwardNodeData(
            user_id=str(sender_id),
            nickname=sender_name,
            content=[message_content]
        )
        
        # 创建转发节点
        forward_node = ForwardNode(data=node_data)
        
        # 创建转发载荷
        forward_payload = ForwardMessagePayload(
            group_id=group_id,
            messages=[forward_node]
        )
        
        ret = await client.api.call_action('send_group_forward_msg', **forward_payload.model_dump())
        logger.info(f"forward_msg: {ret}")