import os

from .....config import get_env
from .....utils import extract_segments, minify_text, filter_kwargs, raise_invalid_params
from .....io import EventBlock
from ...selector import Selector, End
from ...prompt_template import PromptTemplate
from ..base import BaseAgent
from .base import FlowAgent

def get_faq_dir():
    return get_env("ILLUFLY_FAQ")

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

    with open(os.path.join(faq_dir, f"{thread_id}.md"), "w") as f:
        f.write(text)
    return text

class ChatLearn(FlowAgent):
    """
    ChatLearn，用于从对话中学习知识。
    """
    @classmethod
    def available_init_params(cls):
        return {
            "scribe": "负责笔记的ChatAgent",
            "scribe_template": "scribe 所使用的 PromptTemplate, 默认为 PromptTemplate('FLOW/Scribe')",
            **FlowAgent.available_init_params(),
        }

    def __init__(
        self,
        scribe: BaseAgent,
        scribe_template: str=None,
        **kwargs
    ):
        raise_invalid_params(kwargs, self.available_init_params())

        if not isinstance(scribe, BaseAgent):
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
            **filter_kwargs(kwargs, self.available_init_params())
        )
    
    def begin_call(self):
        pass

    def end_call(self):
        pass
        # self._last_output = self.scribe.final_answer
