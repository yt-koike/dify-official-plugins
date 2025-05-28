import json
import os
import uuid
from typing import Any, Generator
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool
from tools.comfyui_client import ComfyUiClient, FileType


class ComfyuiDepthPro(Tool):
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
        precision = tool_parameters.get("precision", None)
        if not precision:
            raise ToolProviderCredentialValidationError(
                "Please input precision")
        images = tool_parameters.get("images") or []
        image_names = []
        for image in images:
            if image.type != FileType.IMAGE:
                continue
            image_name = self.comfyui.upload_image(
                image.filename, image.blob, image.mime_type)
            image_names.append(image_name)

        current_dir = os.path.dirname(os.path.realpath(__file__))
        with open(os.path.join(current_dir, "json", "depth_pro.json")) as file:
            workflow_json = json.load(file)
        workflow_json["6"]["inputs"]["precision"] = precision
        workflow_json["8"]["inputs"]["image"] = image_names[0]

        try:
            image = self.comfyui.generate(workflow_json)[0]
        except Exception as e:
            raise ToolProviderCredentialValidationError(
                f"Failed to generate image: {str(e)}. Maybe install https://github.com/spacepxl/ComfyUI-Depth-Pro on ComfyUI"
            )
        yield self.create_blob_message(
            blob=image,
            meta={"mime_type": "image/png"},
        )
