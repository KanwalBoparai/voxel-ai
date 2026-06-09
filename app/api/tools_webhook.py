"""
Vapi server-tool webhook.

When Vapi's LLM decides to call a tool it POSTs here.
Configure each tool in Vapi's assistant settings with:
  Type: Function (Server)
  Server URL: {APP_BASE_URL}/tools/vapi

Vapi request shape:
  { "message": { "type": "tool-calls",
                 "toolCallList": [{ "id": "...", "name": "...", "arguments": {...} }],
                 "call": { "customer": { "number": "+1..." } } } }

Response shape expected by Vapi:
  { "results": [{ "toolCallId": "...", "result": "<json-string>" }] }
"""
import json
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.services.agent_tools import execute_tool

router = APIRouter(prefix="/tools", tags=["tools"])


@router.post("/vapi")
async def vapi_tool_webhook(request: Request):
    body = await request.json()
    message = body.get("message", {})

    results = []
    for call in message.get("toolCallList", []):
        tool_id   = call.get("id", "")
        name      = call.get("name", "")
        arguments = call.get("arguments", {})

        # arguments may arrive as a string (Vapi sometimes JSON-encodes it)
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {}

        result_str = await execute_tool(name, arguments)
        results.append({"toolCallId": tool_id, "result": result_str})

    return JSONResponse({"results": results})
