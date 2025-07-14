# As an example for genai, 我们并不在实际环境中使用。
from __future__ import annotations

import asyncio

from fastmcp import Client
from google import genai

from lab.config_manager import XnneHangLabSettings, load_settings_file

lab_settings = load_settings_file("lab.toml", XnneHangLabSettings)

mcp_client = Client("./src/lab/mcp/server/timeemi.py")
print("mcp_client", mcp_client)
gemini_client = genai.Client(api_key=lab_settings.agent.llm.gemini.llm_api_key)
print("gemini_client", gemini_client)

# Currently, Gemini’s MCP support only accesses tools from MCP servers—it queries the list_tools endpoint and exposes those functions to the AI. Other MCP features like resources and prompts are not currently supported.
# 目前，Gemini 的 MCP 支持只能访问来自 MCP 服务器的工具--它可以查询 list_tools 端点，并将这些功能公开给人工智能。目前还不支持资源和提示等其他 MCP 功能。
# Currently, the Responses API only accesses tools from MCP servers—it queries the list_tools endpoint and exposes those functions to the AI agent. Other MCP features like resources and prompts are not currently supported.
# 目前，Responses API 只能访问来自 MCP 服务器的工具--它可以查询 list_tools 端点，并将这些功能公开给人工智能代理。目前不支持资源和提示等其他 MCP 功能。
# Gemini 封装的非常高层，但是，似乎因此局限性也太大了。OpenAI 似乎也是如此。 https://gofastmcp.com/integrations/openai


async def main():
    async with mcp_client:
        prompt = await mcp_client.get_prompt_mcp(
            name="limit_time_response", arguments={"time": "十二时二十一分四十一秒", "ask": "现在几点?"}
        )
        print(prompt)
        response = await gemini_client.aio.models.generate_content(
            model="gemini-2.0-flash",
            contents=["现在几点?"],
            config=genai.types.GenerateContentConfig(  # type: ignore
                temperature=0,
                tools=[mcp_client.session],  # Pass the FastMCP client session
            ),
        )
        print(response.text)


if __name__ == "__main__":
    asyncio.run(main())
