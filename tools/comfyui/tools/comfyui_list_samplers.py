from typing import Any, Generator
from httpx import get
from yarl import URL
from dify_plugin.entities.tool import (
    ToolInvokeMessage,
)
from dify_plugin import Tool


class ComfyuiListSamplers(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke tools
        """
        base_url = self.runtime.credentials.get("base_url", "")
        if not base_url:
            yield self.create_text_message("Please input base_url")
        sampling_methods, schedulers = self.get_sample_methods()
        yield self.create_variable_message("sampling_methods", sampling_methods)
        yield self.create_variable_message("schedulers", schedulers)

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
