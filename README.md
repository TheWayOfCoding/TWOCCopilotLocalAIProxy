# TWOC Visual Studio Copilot Local AI Proxy

A lightweight, intelligent API middleware designed to bridge the gap between strict enterprise IDEs (like Visual Studio 2026) and local LLM servers (like `llama.cpp` and `Ollama`).

## ⚠️ The Problem it Solves

When using local AI models with IDE agents like GitHub Copilot, you will eventually hit two massive roadblocks:

1. **The Context Crash (400 Bad Request):** Copilot sends massive hidden payloads containing your workspace context and tool JSON schemas. If this exceeds your local model's context limit (e.g., 32k), the local server crashes.

2. **The IDE Timeout:** Processing 30,000 tokens on a local GPU/CPU takes time. If the local model takes longer than 30 seconds to read the prompt, Visual Studio assumes the server is dead and drops the connection.

## 🚀 The Solution

This proxy sits between Visual Studio and your local AI. It intercepts the payload and provides:

* **Smart Compaction:** If the payload exceeds your budget, it intelligently drops the oldest chat history while strictly pinning your System Prompts and Copilot Tool schemas so the AI never loses its capabilities.
* **Anti-Timeout Heartbeats:** While your local AI is crunching the massive code context, the proxy streams `[Keep-Alive]` packets to Visual Studio to prevent the IDE from timing out.
* **Assistant Prefill Scrubbing:** Converts trailing assistant messages into inline hints rather than letting them cause 400 errors.
* **Dynamic Model Detection:** Automatically queries `/v1/models` on the backend at startup to use whatever model is currently loaded — no manual model name configuration needed.
* **Transparent Pass-Through:** All non-chat endpoints (e.g. `/v1/models`) are forwarded directly to the backend, so IDE model discovery works out of the box.

## 🛠️ Installation & Usage

You can run this proxy directly via Python, or compile it into a standalone Windows `.exe`.

### Option 1: Run via Python (Easiest)

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Run the proxy:
   ```bash
   python proxy.py --max-context 32768 --prompt-budget 28000
   ```

### Option 2: Compile to Standalone .exe (Nuitka)

For the highest native Windows performance, compile the proxy to raw C++ using Nuitka:

```bash
pip install nuitka
python -m nuitka --standalone --onefile --enable-plugin=anti-bloat,implicit-imports --include-package=uvicorn --include-package=fastapi --include-package=tiktoken proxy.py
```

## 🔌 Connecting to Visual Studio 2026

1. Open Visual Studio 2026.
2. Navigate to **Options -> GitHub Copilot -> Local Model / Endpoints**.
3. Set the **Provider** to `Local-AI` (or equivalent).
4. Set the **Base URL** to `http://127.0.0.1:4000/v1` (the proxy's port).
5. Set your Token Limit comfortably high (e.g., `100000`). The proxy will handle the actual hardware limits.


## 🖥️ Backend Server Examples

You can point the proxy to any OpenAI-compatible local server. By default, it targets `http://127.0.0.1:8080` (llama.cpp) or `http://127.0.0.1:11434` (Ollama).

**llama.cpp Example (Highly Recommended for large contexts):**
```bash
llama-server.exe -m Qwen-Coder-35B.gguf --port 8080 -ngl 12 -c 32768 --flash-attn --prompt-cache prompt.cache
```

**Ollama Example:**
```bash
ollama run qwen2.5-coder:32b

# Then run the proxy pointing to Ollama's port:
proxy.exe --target-url http://127.0.0.1:11434
```

## 📜 Command Line Arguments

All arguments can also be set via environment variables, which is useful for running the proxy as a service.

| Argument | Environment Variable | Description | Default |
|---|---|---|---|
| `--max-context` | `PROXY_MAX_CONTEXT` | Total context size of your backend LLM | `32768` |
| `--prompt-budget` | `PROXY_PROMPT_BUDGET` | Max tokens allowed for the prompt | `28000` |
| `--target-url` | `PROXY_TARGET_URL` | The URL of your backend server | `http://127.0.0.1:8080` |
| `--port` | `PROXY_PORT` | The port this proxy listens on | `4000` |
| `--host` | `PROXY_HOST` | The host IP this proxy binds to | `0.0.0.0` |
| `--disable-scrub` | *(flag only)* | Disable trailing assistant prefill scrubbing | `false` |
| `--disable-debug` | *(flag only)* | Disable payload logging to `proxy_debug.log` | `false` |

## 🐞 Debug Logging

By default, the proxy logs the full inbound and outbound JSON payloads to a file called `proxy_debug.log` in the working directory. This is useful for diagnosing compaction behavior or unexpected model responses.

> **Note:** This file can grow large quickly during active use. Pass `--disable-debug` to turn it off.

## License

This project is licensed under the [GPL-3.0 License](LICENSE).
