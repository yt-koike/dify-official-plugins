import json
import os
import uuid
from copy import deepcopy
from enum import Enum
from typing import Any, Generator
from dify_plugin.entities.tool import (
    ToolInvokeMessage,
    ToolParameter,
    ToolParameterOption,
    I18nObject,
)
from dify_plugin import Tool


from tools.comfyui_client import ComfyUiClient, FileType
from dify_plugin.errors.tool import ToolProviderCredentialValidationError


class ModelType(Enum):
    SD15 = 1
    SDXL = 2
    SD3 = 3
    FLUX = 4


class ComfyuiFaceSwap(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke tools
        """
        base_url = self.runtime.credentials.get("base_url", "")
        if not base_url:
            yield self.create_text_message("Please input base_url")
        self.comfyui = ComfyUiClient(base_url)

        images = tool_parameters.get("images") or []
        image_names = []
        for image in images:
            if image.type != FileType.IMAGE:
                continue
            image_name = self.comfyui.upload_image(
                image.filename, image.blob, image.mime_type)
            image_names.append(image_name)
        if len(image_names) <= 1:
            raise ToolProviderCredentialValidationError(
                "Please input two images")

        current_dir = os.path.dirname(os.path.realpath(__file__))
        with open(os.path.join(current_dir, "json", "face_swap.json")) as file:
            draw_options = json.loads(file.read())

        draw_options["15"]["inputs"]["image"] = image_names[0]
        draw_options["22"]["inputs"]["image"] = image_names[1]

        try:
            client_id = str(uuid.uuid4())
            result = self.comfyui.queue_prompt_image(
                client_id, prompt=draw_options)
            image = b""
            for node in result:
                for img in result[node]:
                    if img:
                        image = img
                        break
            yield self.create_blob_message(
                blob=image,
                meta={"mime_type": "image/png"},
            )
        except Exception as e:
            yield self.create_text_message(
                f"Failed to generate image: {str(e)}. Maybe install https://github.com/Gourieff/ComfyUI-ReActor on ComfyUI"
            )
