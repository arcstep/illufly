from datetime import datetime
from typing import Union, List, Dict, Any

class Command():
    """
    长文生成指令。
    """
    def __init__(self, command: str=None, args: Dict[str, Any]=None, output_file: str=None, output_text: str=None, modified_at: str=None):
        self.command = command
        self.args = {k: v for k, v in args.items() if v}
        self.output_file = output_file
        self.output_text = output_text
        self.modified_at = modified_at or datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    def __str__(self):
        return "\n".join([
            self.__repr__()
        ])

    def __repr__(self):
        info = "".join([
            self.args.get('prompt_id', 'DEFAULT_PROMPT'),
            f'[{self.modified_at}]',
            f': {self.output_text[:20]}...' if len(self.output_text) > 20 else self.output_text[:20]
        ])
        return f"Command <{info}>"

    def to_dict(self):
        return {
            'modified_at': self.modified_at,
            'output_file': self.output_file,
            'command': self.command,
            'args': self.args,
            'output_text': self.output_text,
        }
    
    def to_metadata(self):
        return {
            'modified_at': self.modified_at,
            'output_file': self.output_file,
            'command': self.command,
            'args': self.args,
        }

    @classmethod
    def from_dict(cls, dict_):
        return cls(**dict_)