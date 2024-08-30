from ..config import get_env, color_code

class TextBlock():
    def __init__(self, block_type: str, content: str, session_id: str=None):
        self.content = content
        self.block_type = block_type
    
    @property
    def text(self):
        return self.content
    
    @property
    def text_with_print_color(self):
        color = get_env("TEXTLONG_COLOR_DEFAULT")
        if self.block_type == 'text':
            color = get_env("TEXTLONG_COLOR_TEXT")
        elif self.block_type == 'info':
            color = get_env("TEXTLONG_COLOR_INFO")
        elif self.block_type == 'chunk':
            color = get_env("TEXTLONG_COLOR_CHUNK")
        elif self.block_type == 'warn':
            color = get_env("TEXTLONG_COLOR_WARN")
        elif self.block_type == 'final':
            color = get_env("TEXTLONG_COLOR_FINAL")
        elif self.block_type == 'front_matter':
            color = get_env("TEXTLONG_COLOR_FRONT_MATTER")

        return color_code(color) + self.content + "\033[0m"
