import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import (
    AIMessage,
    ToolMessage,
    HumanMessage,
    SystemMessage,
)

from langchain_chinese import (
  ChatZhipuAI,
  _convert_dict_to_message,
)

#
import os
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=True)

#
def test_zhipuai_model_param() -> None:
    llm = ChatZhipuAI(api_key="foo")
    assert llm.api_key == "foo"

    llm = ChatZhipuAI(model="foo")
    assert llm.model == "foo"

#
def test_zhipuai_invoke() -> None:
    llm = ChatZhipuAI(max_tokens=5)
    llm.invoke("讲个笑话来听")

def test_tool_message_dict_to_tool_message() -> None:
    content = json.dumps({"result": "Example #1"})
    tool_call_id = "call_8231168139794583938"
    result = _convert_dict_to_message(
        {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": content,
        }
    )
    assert isinstance(result, ToolMessage)
    assert result.tool_call_id == tool_call_id
    assert result.content == content


def test__convert_dict_to_message_human() -> None:
    message = {"role": "user", "content": "foo"}
    result = _convert_dict_to_message(message)
    expected_output = HumanMessage(content="foo")
    assert result == expected_output


def test__convert_dict_to_message_ai() -> None:
    message = {"role": "assistant", "content": "foo"}
    result = _convert_dict_to_message(message)
    expected_output = AIMessage(content="foo")
    assert result == expected_output


def test__convert_dict_to_message_system() -> None:
    message = {"role": "system", "content": "foo"}
    result = _convert_dict_to_message(message)
    expected_output = SystemMessage(content="foo")
    assert result == expected_output
