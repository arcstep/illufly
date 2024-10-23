import os
from .....config.base import get_env

class TaskFinalAnswerManager():
    """
    从对话过程中自动提取和保存 T/FA 语料。
    """
    def get_tfa_dir(self):
        return os.path.join(get_env("ILLUFLY_XP"), "TFA")

    def save_tfa(self, thread_id: str, task: str, final_answer: str):
        if not thread_id or not task or not final_answer:
            return

        tfa_dir = self.get_tfa_dir()
        if not os.path.exists(tfa_dir):
            os.makedirs(tfa_dir)

        metadata = f'<!-- @metadata {{"class": "{self.__class__.__name__}", "name": "{self.name}"}} -->\n'
        task = f"**任务名称**\n{task}\n\n"
        fa = f"**最终答案**\n{final_answer}"

        with open(os.path.join(tfa_dir, f"{thread_id}.md"), "w") as f:
            f.write(metadata)
            f.write(task)
            f.write(fa)

