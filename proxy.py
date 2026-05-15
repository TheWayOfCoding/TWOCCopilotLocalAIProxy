#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# TWOC Visual Studio Copilot Local AI Proxy
# Copyright (C) 2026 Scott J. Waldron - TheWayOfCoding
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
import os
import sys
import json
import logging
import asyncio
import argparse
import datetime
import tiktoken
import httpx
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse

# ==========================================
# COMMAND LINE ARGUMENTS & CONFIGURATION
# ==========================================
parser = argparse.ArgumentParser(
    description="Universal LLM Compacting Proxy (Anti-Timeout & Payload Truncation)",
    formatter_class=argparse.ArgumentDefaultsHelpFormatter
)

parser.add_argument("--max-context", type=int, 
                    default=int(os.getenv("PROXY_MAX_CONTEXT", 32768)),
                    help="Total context size of your backend LLM (llama.cpp -c limit)")
parser.add_argument("--prompt-budget", type=int, 
                    default=int(os.getenv("PROXY_PROMPT_BUDGET", 28000)),
                    help="Max tokens allowed for the prompt (leaves room for AI output)")
parser.add_argument("--target-url", type=str, 
                    default=os.getenv("PROXY_TARGET_URL", "http://127.0.0.1:8080"),
                    help="The URL of your backend llama.cpp server")
parser.add_argument("--port", type=int, 
                    default=int(os.getenv("PROXY_PORT", 4000)),
                    help="The port this proxy will listen on for Visual Studio")
parser.add_argument("--host", type=str, 
                    default=os.getenv("PROXY_HOST", "0.0.0.0"),
                    help="The host IP this proxy will bind to")
parser.add_argument("--disable-scrub", action="store_true", 
                    help="Disable trailing assistant prefill scrubbing")
parser.add_argument("--disable-debug", action="store_true", 
                    help="Disable writing payloads to proxy_debug.log")

# Parse the arguments passed via command line
args, unknown = parser.parse_known_args()

MAX_CONTEXT_SIZE = args.max_context
PROMPT_BUDGET = args.prompt_budget
LLAMA_CPP_URL = args.target_url
PORT = args.port
HOST = args.host
SCRUB_PREFILLS = not args.disable_scrub
DEBUG_PAYLOADS = not args.disable_debug
DEBUG_LOG_FILE = "proxy_debug.log"

# ==========================================
# PROXY INITIALIZATION
# ==========================================
logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")
logger = logging.getLogger("UniversalProxy")
app = FastAPI(title="Strict LLM Compacting Proxy")
encoder = tiktoken.get_encoding("cl100k_base") 
ACTIVE_MODEL_ID = None

logger.info("="*60)
logger.info("🚀 STRICT COMPACTING PROXY ONLINE (V4)!")
logger.info(f"🛡️ Context Limit: {MAX_CONTEXT_SIZE} | Prompt Budget: {PROMPT_BUDGET}")
logger.info(f"🔗 Target Backend: {LLAMA_CPP_URL} | Listening on: {HOST}:{PORT}")
logger.info(f"🐞 Payload Logging: {'ACTIVE' if DEBUG_PAYLOADS else 'DISABLED'}")
logger.info("="*60)

def dump_to_debug_log(tag: str, payload: dict):
    if not DEBUG_PAYLOADS: return
    try:
        with open(DEBUG_LOG_FILE, "a", encoding="utf-8") as f:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"\n{'='*80}\n[{timestamp}] {tag}\n{'='*80}\n")
            f.write(json.dumps(payload, indent=2) + "\n")
    except Exception as e:
        logger.error(f"Failed to write to debug log: {e}")

async def get_active_model_id() -> str:
    global ACTIVE_MODEL_ID
    if ACTIVE_MODEL_ID: return ACTIVE_MODEL_ID
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(f"{LLAMA_CPP_URL}/v1/models", timeout=5.0)
            if res.status_code == 200:
                models = res.json().get("data", [])
                if models:
                    ACTIVE_MODEL_ID = models[0]["id"]
                    return ACTIVE_MODEL_ID
    except Exception: pass
    return "default"

def extract_all_text(obj):
    if not obj: return ""
    if isinstance(obj, str): return obj
    if isinstance(obj, list): return "\n".join(extract_all_text(i) for i in obj if i)
    if isinstance(obj, dict): return "\n".join(extract_all_text(v) for k, v in obj.items() if isinstance(v, (str, list, dict)))
    return str(obj)

def count_msg_tokens(msg: dict) -> int:
    return len(encoder.encode(json.dumps(msg), disallowed_special=()))

@app.post("/v1/chat/completions")
@app.post("/chat/completions")
@app.post("/api/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    dump_to_debug_log("INBOUND FROM VISUAL STUDIO (Raw)", body)
    
    raw_messages = body.get("messages", [])
    sanitized_messages = []
    
    tools_tokens = 0
    if "tools" in body:
        tools_tokens = len(encoder.encode(json.dumps(body["tools"]), disallowed_special=()))

    for msg in raw_messages:
        if not isinstance(msg, dict): continue
        clean_msg = {"role": msg.get("role", "user")}
        clean_msg["content"] = extract_all_text(msg.get("content", ""))
        
        if "tool_calls" in msg: clean_msg["tool_calls"] = msg["tool_calls"]
        if "tool_call_id" in msg: clean_msg["tool_call_id"] = msg["tool_call_id"]
        if "name" in msg: clean_msg["name"] = msg["name"]

        sanitized_messages.append(clean_msg)

    total_tokens = sum(count_msg_tokens(m) for m in sanitized_messages) + tools_tokens
    clean_body = {k: v for k, v in body.items() if k not in ["messages", "model"]}
    clean_body["model"] = await get_active_model_id()

    if total_tokens > PROMPT_BUDGET:
        logger.warning(f"⚠️ Overflow! {total_tokens} total tokens. Enforcing strict {PROMPT_BUDGET} budget...")
        
        sys_msg = None
        trailing_users = []
        
        if sanitized_messages and sanitized_messages[0].get("role", "").lower() == "system":
            sys_msg = sanitized_messages.pop(0)
            
        while sanitized_messages and sanitized_messages[-1].get("role", "").lower() == "user":
            trailing_users.insert(0, sanitized_messages.pop(-1))
            
        history = sanitized_messages 
        
        sys_tokens = count_msg_tokens(sys_msg) if sys_msg else 0
        trailing_tokens = sum(count_msg_tokens(m) for m in trailing_users)
        
        max_user_allowance = max(1000, PROMPT_BUDGET - sys_tokens - tools_tokens - 1000)
        if trailing_tokens > max_user_allowance and trailing_users:
            encoded_user = encoder.encode(trailing_users[0]["content"], disallowed_special=())
            sliced = encoded_user[-max_user_allowance:]
            trailing_users[0]["content"] = "[System: Older file context truncated...]\n" + encoder.decode(sliced)
            trailing_tokens = sum(count_msg_tokens(m) for m in trailing_users)

        remaining_budget = PROMPT_BUDGET - sys_tokens - tools_tokens - trailing_tokens
        
        kept_history = []
        for msg in reversed(history):
            msg_toks = count_msg_tokens(msg)
            if remaining_budget - msg_toks >= 0:
                kept_history.insert(0, msg)
                remaining_budget -= msg_toks
            else:
                logger.info(f"🗑️ Dropping oldest chat history entirely to respect token budget.")
                break 

        new_messages = []
        if sys_msg: new_messages.append(sys_msg)
        new_messages.extend(kept_history)
        new_messages.extend(trailing_users)
        clean_body["messages"] = new_messages
    else:
        clean_body["messages"] = sanitized_messages

    final_prompt_text = json.dumps(clean_body["messages"]) + json.dumps(clean_body.get("tools", {}))
    final_prompt_tokens = len(encoder.encode(final_prompt_text, disallowed_special=()))
    
    safe_max_tokens = max(512, MAX_CONTEXT_SIZE - final_prompt_tokens)
    clean_body["max_tokens"] = min(clean_body.get("max_tokens", 4096), safe_max_tokens)
    
    logger.info(f"✅ Forwarding exactly ~{final_prompt_tokens} prompt tokens. (Allowed output: {clean_body['max_tokens']})")

    final_messages = clean_body.get("messages", [])
    if SCRUB_PREFILLS:
        while final_messages and final_messages[-1].get("role", "").lower() == "assistant":
            if final_messages[-1].get("tool_calls"): break
            popped_msg = final_messages.pop()
            prefill_text = (popped_msg.get("content", "") or "").strip()
            if prefill_text and final_messages:
                final_messages[-1]["content"] += f"\n\n[System hint: Start your final response with: '{prefill_text}']"
    clean_body["messages"] = final_messages

    dump_to_debug_log(f"OUTBOUND TO LLAMA.CPP (Compacted to {final_prompt_tokens} toks)", clean_body)

    async def stream_generator():
        queue = asyncio.Queue()
        is_done = asyncio.Event()

        async def fetch_stream():
            try:
                async with httpx.AsyncClient() as client:
                    async with client.stream("POST", f"{LLAMA_CPP_URL}/v1/chat/completions", json=clean_body, timeout=1800.0) as response:
                        if response.status_code != 200:
                            err_text = await response.aread()
                            logger.error(f"❌ llama.cpp returned {response.status_code}: {err_text.decode('utf-8', errors='ignore')}")
                            await queue.put(err_text)
                            return
                        async for chunk in response.aiter_bytes():
                            await queue.put(chunk)
            except Exception as e:
                logger.error(f"Stream dropped: {e}")
            finally:
                is_done.set()

        asyncio.create_task(fetch_stream())
        keep_alive_chunk = b'data: {"choices":[{"delta":{"content":""},"index":0,"finish_reason":null}]}\n\n'

        while not is_done.is_set():
            try:
                chunk = await asyncio.wait_for(queue.get(), timeout=10.0)
                yield chunk
            except asyncio.TimeoutError:
                logger.info("⏳ llama.cpp is crunching context... Sending heartbeat to IDE.")
                yield keep_alive_chunk
                
        while not queue.empty():
            yield await queue.get()

    if clean_body.get("stream", False):
        return StreamingResponse(stream_generator(), media_type="text/event-stream")
    else:
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{LLAMA_CPP_URL}/v1/chat/completions", json=clean_body, timeout=1800.0)
            return Response(content=resp.content, status_code=resp.status_code)

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
async def proxy_catch_all(request: Request, path: str):
    url = f"{LLAMA_CPP_URL}/{path}"
    req_body = await request.body()
    async with httpx.AsyncClient() as client:
        resp = await client.request(request.method, url, content=req_body)
        return Response(content=resp.content, status_code=resp.status_code)

if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT)