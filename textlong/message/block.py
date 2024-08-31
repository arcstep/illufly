from ..config import get_env, color_code

class TextBlock():
    def __init__(self, block_type: str, content: str, session_id: str=None):
        self.content = content
        self.block_type = block_type.lower()
    
    @property
    def text(self):
        return self.content
    
    @property
    def text_with_print_color(self):
        color_mapping = {
            'text': "TEXTLONG_COLOR_TEXT",
            'info': "TEXTLONG_COLOR_INFO",
            'warn': "TEXTLONG_COLOR_WARN",
            'final': "TEXTLONG_COLOR_FINAL",
            'chunk': "TEXTLONG_COLOR_CHUNK",
            'front_matter': "TEXTLONG_COLOR_FRONT_MATTER"
        }

        env_var_name = color_mapping.get(self.block_type, "TEXTLONG_COLOR_DEFAULT")
        color = get_env(env_var_name)
        return color_code(color) + self.content + "\033[0m"
