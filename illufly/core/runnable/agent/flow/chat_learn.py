import os
from typing import Union

from .....config import get_env
from .....utils import extract_segments, minify_text, filter_kwargs, raise_invalid_params
from .....io import EventBlock, LocalFileKnowledge
from ...selector import Selector, End
from ...prompt_template import PromptTemplate
from ...message import Messages
from ..base import BaseAgent
from ..chat import ChatAgent
from .base import FlowAgent

class ChatLearn(FlowAgent):
    """
    ChatLearn，用于从对话中学习知识。
    
    属性:
        scribe (ChatAgent): 负责记录和提取知识的智能体
        scribe_template (PromptTemplate): scribe 使用的提示模板
        db (VectorDB): 向量数据库实例，用于存储和检索知识。
            必须与 scribe.vectordbs 中的某个实例相同，以确保知识检索的一致性
    """
    @classmethod
    def allowed_params(cls):
        return {
            "scribe": "负责笔记的ChatAgent，其vectordbs中必须包含与db相同的向量库实例",
            "scribe_template": "scribe 所使用的 PromptTemplate, 默认为 PromptTemplate('FLOW/Scribe')",
            "db": "向量数据库实例，用于存储提取的知识。若不指定则使用scribe中的第一个vectordb",
            **FlowAgent.allowed_params(),
        }

    def __init__(
        self,
        scribe: ChatAgent,
        scribe_template: str=None,
        db=None,
        **kwargs
    ):
        raise_invalid_params(kwargs, self.allowed_params())

        if not isinstance(scribe, ChatAgent):
            raise ValueError("scribe 必须是 ChatAgent 的子类")

        # 验证或获取向量库实例
        if db is None:
            if not scribe.vectordbs:
                raise ValueError("scribe必须配置vectordb才能进行知识学习")
            self.db = next(iter(scribe.vectordbs))
        else:
            # 确保db在scribe的vectordbs中
            if db not in scribe.vectordbs:
                raise ValueError("指定的db必须存在于scribe的vectordbs中，以确保知识检索的一致性")
            self.db = db

        scribe_template = scribe_template or PromptTemplate("FLOW/Scribe")
        self.scribe_template = scribe_template
        scribe.reset_init_memory(scribe_template)
        self.scribe = scribe

        def fetch_faq(agent: BaseAgent):
            final_output_text = agent.last_output
            questions = extract_segments(final_output_text, ('<question>', '</question>'))
            knowledges = extract_segments(final_output_text, ('<knowledge>', '</knowledge>'))
            
            # 保存知识到向量库
            for i, knowledge in enumerate(knowledges):
                q = questions[i] if i < len(questions) else ""
                summary = q if q else knowledge[:100] + "..." if len(knowledge) > 100 else knowledge
                
                # 构建元数据
                meta = {
                    "source": scribe.thread_id,
                    "tags": ["chat_learn", scribe.__class__.__name__]
                }
                
                # 构建文档内容
                meta_text = f'<!-- @meta {str(meta)} -->\n'
                q_text = f"**Question**\n{q}\n\n" if q else ""
                k_text = f"**Knowledge**\n{knowledge}"
                text = meta_text + q_text + k_text
                
                # 直接使用db.add添加文档
                doc_id = self.db.add(
                    text=text,
                    summary=summary,
                    source=scribe.thread_id,
                    tags=["chat_learn", scribe.__class__.__name__]
                )
                yield self.create_event_block("faq", f"保存知识[{doc_id}]：{minify_text(q)} -> {minify_text(knowledge)}")
                scribe.clear()

        def should_fetch():
            if '<knowledge>' in scribe.last_output:
                return "Fetch_FAQ"
            else:
                return "__END__"

        super().__init__(
            {"Scribe": scribe},
            Selector(should_fetch),
            {"Fetch_FAQ": fetch_faq},
            End(),
            **filter_kwargs(kwargs, self.allowed_params())
        )

        self.description = f"我擅长提炼新知识，所有涉及到总结、提炼新知识的地方都可以召唤我来完成任务"
        self.tool_params = {
            "prompt": "请给出你要总结的内容，并在结尾附上一句`请帮我总结其中的新知识`"
        }

    def call(self, prompt: Union[str, ChatAgent], **kwargs):
        return super().call(prompt, **kwargs)

    def begin_call(self, args):
        from ..chat import ChatAgent
        if isinstance(args[0], ChatAgent):
            self.task = args[0].task
            memory = Messages(args[0].memory)
            return [f'请帮我从这对话过程中提取知识：\n\n{str(memory.to_list(style="text"))}']
        else:
            self.task = args[0] if args else None
            return args

