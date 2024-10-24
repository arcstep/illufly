import os
from .....config.base import get_env

class TaskFinalAnswerManager():
    """
    从对话过程中自动提取和保存 T/FA 语料。
    """
    def get_faq_dir(self):
        return get_env("ILLUFLY_TFA")

    def save_faq(self, thread_id: str, task: str, final_answer: str):
        if not thread_id or not task or not final_answer:
            return

        faq_dir = self.get_faq_dir()
        if not os.path.exists(faq_dir):
            os.makedirs(faq_dir)

        metadata = f'<!-- @metadata {{"class": "{self.__class__.__name__}", "name": "{self.name}"}} -->\n'
        task = f"**任务名称**\n{task}\n\n"
        fa = f"**最终答案**\n{final_answer}"

        with open(os.path.join(faq_dir, f"{thread_id}.md"), "w") as f:
            f.write(metadata)
            f.write(task)
            f.write(fa)

