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

from provider import comfyui
from tools.comfyui_client import FileType

SD_TXT2IMG_OPTIONS = {}
LORA_NODE = {
    "inputs": {
        "lora_name": "",
        "strength_model": 1,
        "strength_clip": 1,
        "model": ["11", 0],
        "clip": ["11", 1],
    },
    "class_type": "LoraLoader",
    "_meta": {"title": "Load LoRA"},
}
FluxGuidanceNode = {
    "inputs": {"guidance": 3.5, "conditioning": ["6", 0]},
    "class_type": "FluxGuidance",
    "_meta": {"title": "FluxGuidance"},
}


class ModelType(Enum):
    SD15 = 1
    SDXL = 2
    SD3 = 3
    FLUX = 4


class ComfyuiImg2Img(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke tools
        """
        base_url = self.runtime.credentials.get("base_url", "")
        if not base_url:
            yield self.create_text_message("Please input base_url")
        if tool_parameters.get("model"):
            self.runtime.credentials["model"] = tool_parameters["model"]
        model = self.runtime.credentials.get("model", None)
        if not model:
            yield self.create_text_message("Please input model")
            return
        prompt = tool_parameters.get("prompt", "")
        if not prompt:
            yield self.create_text_message("Please input prompt")
            return
        negative_prompt = tool_parameters.get("negative_prompt", "")
        steps = tool_parameters.get("steps", 20)
        sampler_name = tool_parameters.get("sampler_name", "euler")
        scheduler = tool_parameters.get("scheduler", "normal")
        cfg = tool_parameters.get("cfg", 7.0)
        denoise = tool_parameters.get("denoise", 0.8)
        model_type = tool_parameters.get("model_type", ModelType.SD15.name)
        images = tool_parameters.get("images") or []
        image_names = []
        for image in images:
            if image.type != FileType.IMAGE:
                continue
            blob = httpx.get("http://100.98.35.73" + image.url)
            files = {
                "image": (image.filename, blob, image.mime_type),
                "overwrite": "true",
            }
            res = requests.post(str(base_url + "/upload/image"), files=files)
            image_name = res.json().get("name")
            image_names.append(image_name)
        if len(image_names) == 0:
            yield self.create_text_message("Please input images")
            return
        yield from self.img2img(
            base_url=base_url,
            model=model,
            model_type=model_type,
            denoise=denoise,
            prompt=prompt,
            negative_prompt=negative_prompt,
            image_name=image_names[0],
            steps=steps,
            sampler_name=sampler_name,
            scheduler=scheduler,
            cfg=cfg,
        )

    def get_checkpoints(self) -> list[str]:
        """
        get checkpoints
        """
        try:
            base_url = self.runtime.credentials.get("base_url", None)
            if not base_url:
                return []
            api_url = str(URL(base_url) / "models" / "checkpoints")
            response = get(url=api_url, timeout=(2, 10))
            if response.status_code != 200:
                return []
            else:
                return response.json()
        except Exception as e:
            return []

    def get_loras(self) -> list[str]:
        """
        get loras
        """
        try:
            base_url = self.runtime.credentials.get("base_url", None)
            if not base_url:
                return []
            api_url = str(URL(base_url) / "models" / "loras")
            response = get(url=api_url, timeout=(2, 10))
            if response.status_code != 200:
                return []
            else:
                return response.json()
        except Exception as e:
            return []

    def get_sample_methods(self) -> tuple[list[str], list[str]]:
        """
        get sample method
        """
        try:
            base_url = self.runtime.credentials.get("base_url", None)
            if not base_url:
                return ([], [])
            api_url = str(URL(base_url) / "object_info" / "KSampler")
            response = get(url=api_url, timeout=(2, 10))
            if response.status_code != 200:
                return ([], [])
            else:
                data = response.json()["KSampler"]["input"]["required"]
                return (data["sampler_name"][0], data["scheduler"][0])
        except Exception as e:
            return ([], [])

    def validate_models(self) -> Union[ToolInvokeMessage, list[ToolInvokeMessage]]:
        """
        validate models
        """
        try:
            base_url = self.runtime.credentials.get("base_url", None)
            if not base_url:
                raise ToolProviderCredentialValidationError("Please input base_url")
            model = self.runtime.credentials.get("model", None)
            if not model:
                raise ToolProviderCredentialValidationError("Please input model")
            api_url = str(URL(base_url) / "models" / "checkpoints")
            response = get(url=api_url, timeout=(2, 10))
            if response.status_code != 200:
                raise ToolProviderCredentialValidationError("Failed to get models")
            else:
                models = response.json()
                if len([d for d in models if d == model]) > 0:
                    return self.create_text_message(json.dumps(models))
                else:
                    raise ToolProviderCredentialValidationError(
                        f"model {model} does not exist"
                    )
        except Exception as e:
            raise ToolProviderCredentialValidationError(f"Failed to get models, {e}")

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

    def img2img(
        self,
        base_url: str,
        model: str,
        model_type: str,
        denoise: float,
        prompt: str,
        negative_prompt: str,
        steps: int,
        image_name: str,
        sampler_name: str,
        scheduler: str,
        cfg: float,
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        generate image
        """
        if not SD_TXT2IMG_OPTIONS:
            current_dir = os.path.dirname(os.path.realpath(__file__))
            with open(os.path.join(current_dir, "img2img.json")) as file:
                SD_TXT2IMG_OPTIONS.update(json.load(file))
        draw_options = deepcopy(SD_TXT2IMG_OPTIONS)
        draw_options["3"]["inputs"]["steps"] = steps
        draw_options["3"]["inputs"]["sampler_name"] = sampler_name
        draw_options["3"]["inputs"]["scheduler"] = scheduler
        draw_options["3"]["inputs"]["cfg"] = cfg
        draw_options["3"]["inputs"]["denoise"] = denoise
        draw_options["3"]["inputs"]["seed"] = random.randint(0, 100000000)
        draw_options["14"]["inputs"]["ckpt_name"] = model
        draw_options["6"]["inputs"]["text"] = prompt
        draw_options["7"]["inputs"]["text"] = negative_prompt
        draw_options["10"]["inputs"]["image"] = image_name

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

    def get_runtime_parameters(self) -> list[ToolParameter]:
        parameters = [
            ToolParameter(
                name="prompt",
                label=I18nObject(en_US="Prompt", zh_Hans="Prompt"),
                human_description=I18nObject(
                    en_US="Image prompt, you can check the official documentation of Stable Diffusion",
                    zh_Hans="图像提示词，您可以查看 Stable Diffusion 的官方文档",
                ),
                type=ToolParameter.ToolParameterType.STRING,
                form=ToolParameter.ToolParameterForm.LLM,
                llm_description="Image prompt of Stable Diffusion, you should describe the image you want to generate as a list of words as possible as detailed, the prompt must be written in English.",
                required=True,
            )
        ]
        if self.runtime.credentials:
            try:
                models = self.get_checkpoints()
                if len(models) != 0:
                    parameters.append(
                        ToolParameter(
                            name="model",
                            label=I18nObject(en_US="Model", zh_Hans="Model"),
                            human_description=I18nObject(
                                en_US="Model of Stable Diffusion or FLUX, you can check the official documentation of Stable Diffusion or FLUX",
                                zh_Hans="Stable Diffusion 或者 FLUX 的模型，您可以查看 Stable Diffusion 的官方文档",
                            ),
                            type=ToolParameter.ToolParameterType.SELECT,
                            form=ToolParameter.ToolParameterForm.FORM,
                            llm_description="Model of Stable Diffusion or FLUX, you can check the official documentation of Stable Diffusion or FLUX",
                            required=True,
                            default=models[0],
                            options=[
                                ToolParameterOption(
                                    value=i, label=I18nObject(en_US=i, zh_Hans=i)
                                )
                                for i in models
                            ],
                        )
                    )
                loras = self.get_loras()
                if len(loras) != 0:
                    for n in range(1, 4):
                        parameters.append(
                            ToolParameter(
                                name=f"lora_{n}",
                                label=I18nObject(
                                    en_US=f"Lora {n}", zh_Hans=f"Lora {n}"
                                ),
                                human_description=I18nObject(
                                    en_US="Lora of Stable Diffusion, you can check the official documentation of Stable Diffusion",
                                    zh_Hans="Stable Diffusion 的 Lora 模型，您可以查看 Stable Diffusion 的官方文档",
                                ),
                                type=ToolParameter.ToolParameterType.SELECT,
                                form=ToolParameter.ToolParameterForm.FORM,
                                llm_description="Lora of Stable Diffusion, you can check the official documentation of Stable Diffusion",
                                required=False,
                                options=[
                                    ToolParameterOption(
                                        value=i, label=I18nObject(en_US=i, zh_Hans=i)
                                    )
                                    for i in loras
                                ],
                            )
                        )
                (sample_methods, schedulers) = self.get_sample_methods()
                if len(sample_methods) != 0:
                    parameters.append(
                        ToolParameter(
                            name="sampler_name",
                            label=I18nObject(
                                en_US="Sampling method", zh_Hans="Sampling method"
                            ),
                            human_description=I18nObject(
                                en_US="Sampling method of Stable Diffusion, you can check the official documentation of Stable Diffusion",
                                zh_Hans="Stable Diffusion 的Sampling method，您可以查看 Stable Diffusion 的官方文档",
                            ),
                            type=ToolParameter.ToolParameterType.SELECT,
                            form=ToolParameter.ToolParameterForm.FORM,
                            llm_description="Sampling method of Stable Diffusion, you can check the official documentation of Stable Diffusion",
                            required=True,
                            default=sample_methods[0],
                            options=[
                                ToolParameterOption(
                                    value=i, label=I18nObject(en_US=i, zh_Hans=i)
                                )
                                for i in sample_methods
                            ],
                        )
                    )
                if len(schedulers) != 0:
                    parameters.append(
                        ToolParameter(
                            name="scheduler",
                            label=I18nObject(en_US="Scheduler", zh_Hans="Scheduler"),
                            human_description=I18nObject(
                                en_US="Scheduler of Stable Diffusion, you can check the official documentation of Stable Diffusion",
                                zh_Hans="Stable Diffusion 的Scheduler，您可以查看 Stable Diffusion 的官方文档",
                            ),
                            type=ToolParameter.ToolParameterType.SELECT,
                            form=ToolParameter.ToolParameterForm.FORM,
                            llm_description="Scheduler of Stable Diffusion, you can check the official documentation of Stable Diffusion",
                            required=True,
                            default=schedulers[0],
                            options=[
                                ToolParameterOption(
                                    value=i, label=I18nObject(en_US=i, zh_Hans=i)
                                )
                                for i in schedulers
                            ],
                        )
                    )
                parameters.append(
                    ToolParameter(
                        name="model_type",
                        label=I18nObject(en_US="Model Type", zh_Hans="Model Type"),
                        human_description=I18nObject(
                            en_US="Model Type of Stable Diffusion or Flux, you can check the official documentation of Stable Diffusion or Flux",
                            zh_Hans="Stable Diffusion 或 FLUX 的模型类型，您可以查看 Stable Diffusion 或 Flux 的官方文档",
                        ),
                        type=ToolParameter.ToolParameterType.SELECT,
                        form=ToolParameter.ToolParameterForm.FORM,
                        llm_description="Model Type of Stable Diffusion or Flux, you can check the official documentation of Stable Diffusion or Flux",
                        required=True,
                        default=ModelType.SD15.name,
                        options=[
                            ToolParameterOption(
                                value=i, label=I18nObject(en_US=i, zh_Hans=i)
                            )
                            for i in ModelType.__members__
                        ],
                    )
                )
            except:
                pass
        return parameters
