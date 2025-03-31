from docling.document_converter import DocumentConverter
from docling.datamodel.pipeline_options import PictureDescriptionApiOptions
import os
from dotenv import load_dotenv

load_dotenv()

# Enable connections to remote services
pipeline_options.enable_remote_services=True  # <-- this is required!

# Example using a model running locally, e.g. via VLLM
# $ vllm serve MODEL_NAME
pipeline_options.picture_description_options = PictureDescriptionApiOptions(
    url=os.getenv("OPENAI_BASE_URL") + "/v1/chat/completions",
    params=dict(
        model="MODEL NAME",
        seed=42,
        max_completion_tokens=200,
    ),
    prompt="Describe the image in three sentences. Be consise and accurate.",
    timeout=90,
)

source = "https://arxiv.org/pdf/2408.09869"  # document per local path or URL
converter = DocumentConverter()
result = converter.convert(source)
print(result.document.export_to_markdown())  # output: "## Docling Technical Report[...]"po