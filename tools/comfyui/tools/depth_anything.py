import json
import mimetypes
import os
from typing import Any, Generator
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool


from tools.comfyui_client import ComfyUiClient, FileType


class ComfyuiDepthAnything(Tool):
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
        model = tool_parameters.get("model", None)
        if not model:
            raise ToolProviderCredentialValidationError("Please input model")

        images = tool_parameters.get("images") or []
        image_names = []
        for image in images:
            if image.type != FileType.IMAGE:
                continue
            image_name = self.comfyui.upload_image(
                image.filename, image.blob, image.mime_type)
            image_names.append(image_name)

        current_dir = os.path.dirname(os.path.realpath(__file__))
        with open(os.path.join(current_dir, "json", "depth_anything.json")) as file:
            workflow_json = json.load(file)
        workflow_json["2"]["inputs"]["model"] = model
        workflow_json["3"]["inputs"]["image"] = image_names[0]

        try:
            output_images = self.comfyui.generate_image_by_prompt(
                workflow_json)
        except Exception as e:
            raise ToolProviderCredentialValidationError(
                f"Failed to generate image: {str(e)}. Maybe install https://github.com/kijai/ComfyUI-DepthAnythingV2 on ComfyUI")
        for img in output_images:
            yield self.create_blob_message(
                blob=img["data"],
                meta={"filename": img["filename"], "mime_type": mimetypes.guess_type(
                    img["filename"])[0] or "image/png"},
            )
