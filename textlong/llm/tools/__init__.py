from langchain.pydantic_v1 import BaseModel, Field
from langchain.tools import tool
from langchain_core.utils.function_calling import convert_to_openai_tool
from langchain_core.tools import StructuredTool

from .python_code import create_python_code_tool

