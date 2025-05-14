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

import httpx
from tools.comfyui_client import ComfyUiClient, FileType


class DownloadCivitAI(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke tools
        """
        base_url = self.runtime.credentials.get("base_url", "")
        if not base_url:
            yield self.create_text_message("Please input base_url")
            return
        civitai_api_key = self.runtime.credentials.get("civitai_api_key", "")
        if not civitai_api_key:
            yield self.create_text_message("Please input civitai_api_key")
            return
        self.comfyui = ComfyUiClient(base_url)

        current_dir = os.path.dirname(os.path.realpath(__file__))
        with open(os.path.join(current_dir, "download_civitai.json")) as file:
            draw_options = json.loads(file.read())

        model_id = tool_parameters.get("model_id", "")
        version_id = tool_parameters.get("version_id", "")
        save_dir = tool_parameters.get("save_dir", "")
        try:
            model_data = httpx.get(
                f"https://civitai.com/api/v1/models/{model_id}").json()
        except:
            yield self.create_text_message(f"Model {model_id} not found.")
            return
        model_name = model_data["name"]
        model_detail = None
        for past_model in model_data["modelVersions"]:
            if past_model["id"] == version_id:
                model_detail = past_model
                break
        if model_detail is None:
            yield self.create_text_message(f"Version {version_id} of model {model_name} not found.")
            return
        model_filenames = [file["name"] for file in model_detail["files"]]

        draw_options["11"]["inputs"]["model_id"] = model_id
        draw_options["11"]["inputs"]["version_id"] = version_id
        draw_options["11"]["inputs"]["token_id"] = civitai_api_key
        draw_options["11"]["inputs"]["save_dir"] = save_dir

        try:
            client_id = str(uuid.uuid4())
            self.comfyui.queue_prompt_image(client_id, prompt=draw_options)
            yield self.create_variable_message("model_name", model_name)
            yield self.create_variable_message("model_filename", model_filenames[0])
        except Exception as e:
            yield self.create_text_message(
                f"Failed to generate image: {str(e)}. Maybe install https://github.com/ciri/comfyui-model-downloader on ComfyUI"
            )
