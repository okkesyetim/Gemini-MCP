import asyncio
import os
import sys
import json
import re
from typing import Optional
from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()


class GeminiMCPChat:
    def __init__(self):
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        try:
            api_key = os.environ.get("GEMINI_API_KEY")
            if not api_key:
                raise KeyError
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel(model_name="gemini-1.5-flash")
        except KeyError:
            print("ERROR: GEMINI_API_KEY not found in the .env file.")
            sys.exit(1)

    async def connect_to_server(self, server_script_path: str):
        print("[CLIENT] Attempting to connect to MCP server...")
        command = sys.executable
        server_params = StdioServerParameters(command=command, args=[server_script_path])

        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.read, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.read, self.write))
        await self.session.initialize()
        response = await self.session.list_tools()
        print(f"[CLIENT] Successfully connected. Available tools: {[tool.name for tool in response.tools]}")

    def _create_decision_prompt(self, query: str, tools: list) -> str:
        tools_as_json_string = json.dumps(tools, indent=2)
        return f"""
You are an expert assistant that decides whether to use a tool to answer a user's request.
You have access to the following tools:
{tools_as_json_string}

The user's request is: "{query}"

Based on the request, decide which action to take:
1. If a tool is necessary, respond with ONLY a single JSON object in the format: {{"type": "tool", "name": "tool_name", "parameter": {{"arg1": "value1", ...}}}}
2. If no tool is needed, respond with ONLY a single JSON object in the format: {{"type": "text", "text": "Your conversational response here."}}

Do not add any explanations or markdown formatting like ```json.
"""

    def _create_summary_prompt(self, original_query: str, tool_name: str, tool_result: str) -> str:
        return f"""
You are a helpful assistant. You have just used a tool to get information for a user.
- The user's original query was: "{original_query}"
- You decided to call the tool: "{tool_name}"
- The result from the tool is: "{tool_result}"

Based on this, provide a friendly, natural language summary to the user.
Directly answer their original question conversationally. Do not mention the tool name or the raw data.
"""

    async def process_query(self, query: str):
        print(f"\n[CLIENT] > Processing new query: '{query}'")

        # 1. Get the list of available tools from the server
        print("[CLIENT] >> Sending 'ListToolsRequest' to MCP server...")
        tool_list_response = await self.session.list_tools()
        available_tools = [{"name": t.name, "description": t.description, "input_schema": t.inputSchema} for t in
                           tool_list_response.tools]
        print("[CLIENT] << Received 'ListToolsResponse' from MCP server.")

        # 2. Ask Gemini to make a decision: use a tool or reply with text?
        prompt = self._create_decision_prompt(query, available_tools)
        print("\n" + "=" * 25 + " [PROMPT FOR GEMINI: Decision Making] " + "=" * 25)
        print(prompt.strip())
        print("=" * 80 + "\n")

        response = await self.model.generate_content_async(prompt)

        try:
            raw_response_text = response.text.strip()
            print(f"[GEMINI] < Raw decision response from Gemini: {raw_response_text}")
            cleaned_json_text = re.sub(r"```json\n|\n```", "", raw_response_text, flags=re.MULTILINE).strip()
            decision = json.loads(cleaned_json_text)
            print(f"[CLIENT] * Gemini's decision parsed successfully: {decision}")
        except (json.JSONDecodeError, AttributeError, ValueError) as e:
            print(f"[CLIENT] !! ERROR: Could not parse Gemini's response as JSON. Error: {e}")
            print(f"[CLIENT] Displaying the raw text as a fallback response.")
            print("\n[FINAL RESPONSE] Gemini:\n", response.text)
            return

        # 3. Act on Gemini's decision
        if decision.get("type") == "tool":
            tool_name = decision.get("name")
            tool_args = decision.get("parameter", {})
            print(f"[CLIENT] -> Gemini chose to use the '{tool_name}' tool with args: {tool_args}")

            try:
                # 4. Call the tool via the MCP server
                print(f"[CLIENT] >> Sending 'CallToolRequest' for '{tool_name}' to MCP server...")
                tool_result_obj = await self.session.call_tool(tool_name, tool_args)
                print(f"[CLIENT] << Received 'CallToolResponse' from MCP server.")
                tool_output_text = "".join([c.text for c in tool_result_obj.content if c.type == 'text'])
                print(
                    f"[CLIENT] * Extracted tool result (first 300 chars): {tool_output_text[:300].replace('\n', ' ')}...")

                # 5. Ask Gemini to summarize the tool's result
                summary_prompt = self._create_summary_prompt(query, tool_name, tool_output_text)
                print("\n" + "=" * 25 + " [PROMPT FOR GEMINI: Summarization] " + "=" * 26)
                print(summary_prompt.strip())
                print("=" * 80 + "\n")

                summary_response = await self.model.generate_content_async(summary_prompt)
                print(f"[GEMINI] < Raw summary response from Gemini: {summary_response.text.strip()}")
                print("\n[FINAL RESPONSE] Gemini:")
                print(summary_response.text)

            except Exception as e:
                print(f"[CLIENT] !! ERROR during tool call or summarization: {e}")
                print(
                    "\n[FINAL RESPONSE] Gemini:\nSorry, I encountered an error while trying to process your request with a tool.")

        elif decision.get("type") == "text":
            print("[CLIENT] -> Gemini chose to respond with text directly.")
            print("\n[FINAL RESPONSE] Gemini:")
            print(decision.get("text", "I received a text response, but it was empty."))
        else:
            print(f"[CLIENT] !! ERROR: Received an unknown decision type from Gemini: {decision}")
            print(
                "\n[FINAL RESPONSE] Gemini:\nI'm not sure how to proceed with that. Please try rephrasing your request.")

    async def chat_loop(self):
        print("\n--- Gemini MCP Chat Client ---")
        print("Type your query or 'quit' to exit.")
        print("Example: 'what are the weather alerts for NY?' or 'forecast for san francisco'")

        while True:
            try:
                query = input("\nYou: ").strip()
                if query.lower() in ['quit', 'exit']: break
                if not query: continue
                await self.process_query(query)
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"\nAn unexpected error occurred in the chat loop: {e}")

    async def cleanup(self):
        print("\n[CLIENT] Cleaning up and closing connections...")
        await self.exit_stack.aclose()


async def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    server_script = os.path.join(script_dir, "..", "mcp_server", "weather_server.py")

    if not os.path.exists(server_script):
        print(f"FATAL ERROR: Server script not found at path: {server_script}")
        sys.exit(1)

    chat_client = GeminiMCPChat()
    try:
        await chat_client.connect_to_server(server_script)
        await chat_client.chat_loop()
    finally:
        await chat_client.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nProgram terminated by user.")