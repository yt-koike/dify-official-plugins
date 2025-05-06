import json
import os
import random
import uuid
from copy import deepcopy
from enum import Enum
from typing import Any, Generator, Union
import httpx
import requests
import websocket
from httpx import get, post
from yarl import URL
from dify_plugin.entities.tool import (
    ToolInvokeMessage,
    ToolParameter,
    ToolParameterOption,
    I18nObject,
)
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from dify_plugin import Tool


from tools.comfyui_client import FileType


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
        precision = tool_parameters.get("precision", None)
        if not precision:
            yield self.create_text_message("Please input precision")
            return
        image_server_url = self.runtime.credentials.get("image_server_url", "")
        if not image_server_url:
            yield self.create_text_message("Please input image_server_url")
        images = tool_parameters.get("images") or []
        image_names = []
        for image in images:
            if image.type != FileType.IMAGE:
                continue
            blob = httpx.get(image_server_url.rstrip("/") + image.url, timeout=3)
            files = {
                "image": (image.filename, blob, image.mime_type),
                "overwrite": "true",
            }
            res = requests.post(str(base_url + "/upload/image"), files=files)
            image_name = res.json().get("name")
            image_names.append(image_name)

        current_dir = os.path.dirname(os.path.realpath(__file__))
        with open(os.path.join(current_dir, "comfyui_depth_pro.json")) as file:
            draw_options = json.load(file)
        draw_options["6"]["inputs"]["precision"] = precision
        draw_options["8"]["inputs"]["image"] = image_names[0]

        try:
            client_id = str(uuid.uuid4())
            result = self.queue_prompt_image(base_url, client_id, prompt=draw_options)
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
            yield self.create_text_message(f"Failed to generate image: {str(e)}")

    def get_history(self, base_url, prompt_id):
        """
        get history
        """
        url = str(URL(base_url) / "history")
        respond = get(url, params={"prompt_id": prompt_id}, timeout=(2, 10))
        return respond.json()

    def download_image(self, base_url, filename, subfolder, folder_type):
        """
        download image
        """
        url = str(URL(base_url) / "view")
        response = get(
            url,
            params={"filename": filename, "subfolder": subfolder, "type": folder_type},
            timeout=(2, 10),
        )
        return response.content

    def queue_prompt_image(self, base_url, client_id, prompt):
        """
        send prompt task and rotate
        """
        url = str(URL(base_url) / "prompt")
        respond = post(
            url,
            data=json.dumps({"client_id": client_id, "prompt": prompt}),
            timeout=(2, 10),
        )
        prompt_id = respond.json()["prompt_id"]
        ws = websocket.WebSocket()
        if "https" in base_url:
            ws_url = base_url.replace("https", "ws")
        else:
            ws_url = base_url.replace("http", "ws")
        ws.connect(str(URL(f"{ws_url}") / "ws") + f"?clientId={client_id}", timeout=120)
        output_images = {}
        while True:
            out = ws.recv()
            if isinstance(out, str):
                message = json.loads(out)
                if message["type"] == "executing":
                    data = message["data"]
                    if data["node"] is None and data["prompt_id"] == prompt_id:
                        break
                elif message["type"] == "status":
                    data = message["data"]
                    if data["status"]["exec_info"]["queue_remaining"] == 0 and data.get(
                        "sid"
                    ):
                        break
            else:
                continue
        history = self.get_history(base_url, prompt_id)[prompt_id]
        for o in history["outputs"]:
            for node_id in history["outputs"]:
                node_output = history["outputs"][node_id]
                if "images" in node_output:
                    images_output = []
                    for image in node_output["images"]:
                        image_data = self.download_image(
                            base_url,
                            image["filename"],
                            image["subfolder"],
                            image["type"],
                        )
                        images_output.append(image_data)
                    output_images[node_id] = images_output
        ws.close()
        return output_images
