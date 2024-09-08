from ..config import get_env, color_code

class TextBlock():
    def __init__(self, block_type: str, content: str, session_id: str=None):
        self.content = str(content)
        self.block_type = block_type
    
    def __str__(self):
        return self.content
    
    def __repr__(self):
        return f"TextBlock(block_type=<{self.block_type}>, content=<{self.content}>)"
        
    @property
    def text(self):
        return self.content
    
    @property
    def text_with_print_color(self):
        color_mapping = {
            'text': "TEXTLONG_COLOR_TEXT",
            'code': "TEXTLONG_COLOR_INFO",
            'tool_resp': "TEXTLONG_COLOR_INFO",
            'tools_call': "TEXTLONG_COLOR_INFO",
            'info': "TEXTLONG_COLOR_INFO",
            'warn': "TEXTLONG_COLOR_WARN",
            'final': "TEXTLONG_COLOR_FINAL",
            'chunk': "TEXTLONG_COLOR_CHUNK",
            'front_matter': "TEXTLONG_COLOR_FRONT_MATTER",
            'END': "TEXTLONG_COLOR_INFO"
        }

        env_var_name = color_mapping.get(self.block_type, "TEXTLONG_COLOR_DEFAULT")
        color = get_env(env_var_name)
        return color_code(color) + self.content + "\033[0m"

def yield_block(block_type: str, output_text: str):
    yield TextBlock(block_type, output_text)

