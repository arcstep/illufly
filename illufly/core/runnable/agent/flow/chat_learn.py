import os
from typing import Union

from .....config import get_env
from .....utils import extract_segments, minify_text, filter_kwargs, raise_invalid_params
from .....io import EventBlock
from ...selector import Selector, End
from ...prompt_template import PromptTemplate
from ...message import Messages
from ..base import BaseAgent
from ..chat import ChatAgent
from .base import FlowAgent

def get_faq_dir():
    return get_env("ILLUFLY_CHAT_LEARN")

def save_faq(thread_id: str, knowledge: str, question: str="", metadata: dict={}):
    if not thread_id or not knowledge:
        return

    faq_dir = get_faq_dir()
    if not os.path.exists(faq_dir):
        os.makedirs(faq_dir)

    metadata = f'<!-- @metadata {str(metadata) if metadata else ""} -->\n'
    q = f"**Question**\n{question}\n\n"
    k = f"**Knowledge**\n{knowledge}"
    text = (metadata + q + k) or ""

    with open(os.path.join(faq_dir, f"{thread_id}.md"), "w", encoding="utf-8") as f:
        f.write(text)
    return text

class ChatLearn(FlowAgent):
    """
    ChatLearn，用于从对话中学习知识。
    """
    @classmethod
    def allowed_params(cls):
        return {
            "scribe": "负责笔记的ChatAgent",
            "scribe_template": "scribe 所使用的 PromptTemplate, 默认为 PromptTemplate('FLOW/Scribe')",
            **FlowAgent.allowed_params(),
        }

    def __init__(
        self,
        scribe: ChatAgent,
        scribe_template: str=None,
        **kwargs
    ):
        raise_invalid_params(kwargs, self.allowed_params())

        if not isinstance(scribe, ChatAgent):
            raise ValueError("scribe 必须是 ChatAgent 的子类")

        scribe_template = scribe_template or PromptTemplate("FLOW/Scribe")
        self.scribe_template = scribe_template

        scribe.reset_init_memory(scribe_template)
        self.scribe = scribe

        def fetch_faq(agent: BaseAgent):
            final_output_text = agent.last_output
            questions = extract_segments(final_output_text, '<question>', '</question>')
            knowledges = extract_segments(final_output_text, '<knowledge>', '</knowledge>')
            metadata = {"class": scribe.__class__.__name__, "name": scribe.name, "thread_id": scribe.thread_id}

            # 保存 Q/K 语料
            for i, knowledge in enumerate(knowledges):
                q = questions[i] if i < len(questions) else ""
                text = save_faq(scribe.thread_id, knowledge, q, metadata)
                yield EventBlock("faq", f"保存知识到[{scribe.thread_id}]：{minify_text(q)} -> {minify_text(knowledge)}")
                scribe.clear()
                if scribe.default_vdb:
                    scribe.default_vdb.load_text(text, source=scribe.thread_id)

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
            return [f'请帮我从这段对话过程中提取知识：\n\n{str(memory.to_list(style="text"))}']
        else:
            self.task = args[0] if args else None
            return args

