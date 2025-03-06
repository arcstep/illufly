import logging
import json

def extract_json_text(text: str, logger: logging.Logger) -> dict:
    """提取json文本"""
    try:
        json_text = text.strip()
        if json_text.startswith("```json"):
            json_text = json_text[len("```json"):].strip()
        if json_text.endswith("```"):
            json_text = json_text[:-len("```")]
        return json.loads(json_text)
    except Exception as e:
        logger.warning(f"提取json文本失败: {e}\n\n FROM TEXT: {text}")
        return {}
