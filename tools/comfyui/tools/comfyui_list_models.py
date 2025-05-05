from typing import Any, Generator
from httpx import get
from yarl import URL
from dify_plugin.entities.tool import (
    ToolInvokeMessage,
)
from dify_plugin import Tool


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
        yield self.create_variable_message("models", self.get_checkpoints())

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
