# TWOC Visual Studio Copilot Local AI Proxy

A lightweight, intelligent API middleware designed to bridge the gap between Visual Studio 2026's built-in Copilot chat system using the Ollama option and local LLM servers (like `llama.cpp` and `Ollama`).

## ⚠️ The Problem it Solves

When using local AI models with IDE agents like GitHub Copilot, you will eventually hit two roadblocks:

1. **The Context Crash (400 Bad Request):** Copilot sends large hidden payloads containing your workspace context and tool JSON schemas. If this exceeds your local model's context limit (e.g., the default of 32k this script uses), the local server crashes.

2. **The IDE Timeout:** Processing 30,000 tokens on a local GPU/CPU can take time depending on your hardware. If the local model takes longer than 30 seconds to read the prompt, Visual Studio assumes the server is dead and drops the connection. This allows you to run large models on modest hardware as long as you are okay with waiting.

## 🚀 The Solution

This proxy sits between Visual Studio and your local LLM. It intercepts the payload and provides:

* **Smart Compaction:** If the payload exceeds your budget, it intelligently drops the oldest chat history while strictly pinning your System Prompts and Copilot Tool schemas so the AI never loses its capabilities.
* **Anti-Timeout Heartbeats:** While your local AI is processing the massive code context, the proxy streams `[Keep-Alive]` packets to Visual Studio to prevent the IDE from timing out.
* **Assistant Prefill Scrubbing:** Converts trailing assistant messages into inline hints rather than letting them cause 400 errors.
* **Dynamic Model Detection:** Automatically queries `/v1/models` on the backend at startup to use whatever model is currently loaded, no manual model name configuration needed.
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

<img width="478" height="556" alt="vs-copilot-chat" src="https://github.com/user-attachments/assets/cbc508c9-6210-4c63-98c5-2599729f3428" />

1. Open Visual Studio 2026
2. Make sure that the Copilot panel is open.  
3. Access the feature of adding providers through the Copilot chat panel inside the drop-down list where built-in options like Claude and ChatGPT exist.
4. Set the **Provider** to Ollama.
5. Set the **Base URL** to `http://127.0.0.1:4000/v1` (the proxy's port).
6. Give your AI a name and use that URL again for the related field. It does not need to be the filename of the model because the proxy handles that by communicating with the AI server.
7. The two token limits can be left at their default values. The proxy will handle the actual hardware limits.
8. Save and then make sure that entry is checked. From a drop-down provider list, you should see your local model under the Claude and GPT options. 
<img width="609" height="531" alt="vs2016-byom-ollama" src="https://github.com/user-attachments/assets/c980edf3-8ef6-4050-8032-2f8c1669e95d" />

## 🖥️ Backend Server Examples

You can point the proxy to any OpenAI-compatible local server. By default, it targets `http://127.0.0.1:8080` (llama.cpp) or `http://127.0.0.1:11434` (Ollama).

**llama.cpp Example (Highly Recommended for large contexts):**
```bash
llama-server.exe -m Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf --port 8080 -ngl 9 -t 12 -c 32768 -b 4096 -ub 512 --flash-attn on -ctk q8_0 -ctv q8_0 --alias qwen-coder --mlock
```
Take note that you likely need the coder alias for it to communicate with the IDE in an agentic way.

Here's an additional example for llama.cpp, in this case a smaller LLM meant to fit into 8GB of VRAM ON A GPU. So far I haven't had luck with this size of model doing agentic programming with tool calling: 
```bash
llama-server.exe -m gemma-4-E4B-it-IQ4_NL.gguf --port 8080 -ngl 99 -c 32768 -b 4096 --flash-attn on -ctk q8_0 -ctv q8_0 --alias gemma-coder
```

**Ollama Example:**
```bash
ollama run Qwen3.6-35B-A3B-UD-Q4_K_XL

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
| `--enable-debug` | *(flag only)* | Enable payload logging to `proxy_debug.log` | `false` |

## 🐞 Debug Logging

By default, the proxy does NOT log the full inbound and outbound JSON payloads. 

If you need to diagnose compaction behavior or unexpected model responses, pass `--enable-debug` to turn it on. This will write full payloads to a file called `proxy_debug.log` in the working directory.

> **Note:** This file can grow large quickly during active use, so it is recommended to keep it disabled during normal operation.

## License

This project is licensed under the [AGPL-3.0 License](LICENSE).
```
