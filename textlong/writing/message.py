from ..config import get_env, color_code

class TextChunk():
    def __init__(self, mode: str, content: str, session_id: str=None):
        self.content = content
        self.mode = mode
    
    @property
    def text(self):
        return self.content
    
    @property
    def text_with_print_color(self):
        color = get_env("TEXTLONG_COLOR_DEFAULT")
        if self.mode == 'text':
            color = get_env("TEXTLONG_COLOR_TEXT")
        elif self.mode == 'info':
            color = get_env("TEXTLONG_COLOR_INFO")
        elif self.mode == 'chunk':
            color = get_env("TEXTLONG_COLOR_CHUNK")
        elif self.mode == 'warn':
            color = get_env("TEXTLONG_COLOR_WARN")
        elif self.mode == 'final':
            color = get_env("TEXTLONG_COLOR_FINAL")
        elif self.mode == 'front_matter':
            color = get_env("TEXTLONG_COLOR_FRONT_MATTER")

        return color_code(color) + self.content + "\033[0m"
