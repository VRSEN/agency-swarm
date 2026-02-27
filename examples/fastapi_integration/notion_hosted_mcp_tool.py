"""Notion HostedMCPTool + FastAPI OAuth example.

This example uses OpenAI's remote MCP tool (`HostedMCPTool`) pointed at Notion's
hosted MCP server.

In production you should run this via FastAPI streaming, so OAuth redirects are
sent to your frontend as SSE events (instead of opening a browser on the server).

Run:
    PORT=8081 uv run python examples/fastapi_integration/notion_hosted_mcp_tool.py

Then open:
    http://127.0.0.1:8081/demo/notion

This demo page:
- Starts a streaming run against `/notion_hosted_mcp/get_response_stream`
- Listens for `event: oauth_redirect`
- Opens the Notion OAuth URL in a new tab (or shows it if popups are blocked)
- Continues streaming after the callback completes
"""

import os

from dotenv import load_dotenv
from fastapi.responses import HTMLResponse
from openai.types.responses.tool_param import Mcp

from agency_swarm import Agency, Agent, HostedMCPTool, run_fastapi
from agency_swarm.integrations.fastapi_utils.oauth_support import OAuthStateRegistry

load_dotenv()

PORT = int(os.getenv("PORT", "8000"))
# For local testing, point OAuth callbacks at the same FastAPI server port.
# Notion validates the redirect URI; use the built-in FastAPI OAuth callback route.
os.environ["OAUTH_CALLBACK_URL"] = f"http://127.0.0.1:{PORT}/auth/callback"

DEMO_PAGE = """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Notion Hosted MCP OAuth Demo</title>
    <style>
      body { font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial; margin: 24px; }
      input, textarea, button { font: inherit; }
      textarea { width: 100%; height: 110px; }
      .row { display: flex; gap: 12px; align-items: center; margin: 12px 0; }
      .row > * { flex: 1; }
      #log { white-space: pre-wrap; background: #0b1020; color: #e6e6e6; padding: 12px; border-radius: 8px; }
      .hint { color: #555; font-size: 14px; }
      .btn { padding: 10px 14px; border-radius: 8px; border: 1px solid #ddd; cursor: pointer; }
      .btn-primary { background: #111827; color: white; border-color: #111827; }
      a { word-break: break-all; }
    </style>
  </head>
  <body>
    <h2>Notion Hosted MCP OAuth Demo</h2>
    <div class="hint">
      This page starts a streaming run and handles OAuth redirects like a SaaS frontend:
      it opens the auth URL in a new tab and keeps the stream open.
    </div>

    <div class="row">
      <div>
        <label for="userId"><strong>X-User-Id</strong></label><br/>
        <input id="userId" value="demo_user" />
      </div>
      <div>
        <button id="startBtn" class="btn btn-primary">Start</button>
      </div>
    </div>

    <label for="message"><strong>Message</strong></label><br/>
    <textarea id="message">Search my Notion for any page and summarize it.</textarea>

    <div class="row">
      <div>
        <strong>Auth URL</strong>: <span id="authUrl">(none yet)</span>
      </div>
      <div>
        <button id="openAuthBtn" class="btn" disabled>Open auth URL</button>
      </div>
    </div>

    <h3>Stream</h3>
    <div id="log"></div>

    <script>
      const logEl = document.getElementById("log");
      const authUrlEl = document.getElementById("authUrl");
      const openAuthBtn = document.getElementById("openAuthBtn");
      let lastAuthUrl = null;

      function log(msg) {
        logEl.textContent += msg + "\\n";
        logEl.scrollTop = logEl.scrollHeight;
      }

      function setAuthUrl(url) {
        lastAuthUrl = url;
        authUrlEl.innerHTML = `<a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a>`;
        openAuthBtn.disabled = false;
      }

      openAuthBtn.addEventListener("click", () => {
        if (!lastAuthUrl) return;
        window.open(lastAuthUrl, "_blank", "noopener,noreferrer");
      });

      async function start() {
        logEl.textContent = "";
        authUrlEl.textContent = "(none yet)";
        openAuthBtn.disabled = true;
        lastAuthUrl = null;

        const userId = document.getElementById("userId").value;
        const message = document.getElementById("message").value;

        log("Starting stream...");
        const resp = await fetch("/notion_hosted_mcp/get_response_stream", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-User-Id": userId,
          },
          body: JSON.stringify({ message }),
        });

        if (!resp.ok || !resp.body) {
          log(`HTTP ${resp.status}: ${await resp.text()}`);
          return;
        }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        function handleEventChunk(chunk) {
          const lines = chunk.split("\\n");
          let eventName = "message";
          const dataLines = [];
          for (const line of lines) {
            if (line.startsWith("event:")) {
              eventName = line.slice(6).trim();
            } else if (line.startsWith("data:")) {
              dataLines.push(line.slice(5).trimStart());
            }
          }
          const dataText = dataLines.join("\\n");

          let parsed = null;
          try { parsed = JSON.parse(dataText); } catch {}

          if (eventName === "oauth_redirect" && parsed && parsed.auth_url) {
            setAuthUrl(parsed.auth_url);
            log(`[oauth_redirect] state=${parsed.state} server=${parsed.server}`);
            const opened = window.open(parsed.auth_url, "_blank", "noopener,noreferrer");
            if (!opened) {
              log("Popup blocked. Click 'Open auth URL'.");
            }
            return;
          }

          if (eventName === "oauth_status" && parsed) {
            log(`[oauth_status] state=${parsed.state} server=${parsed.server}`);
            return;
          }

          if (eventName === "meta" && parsed && parsed.run_id) {
            log(`[meta] run_id=${parsed.run_id}`);
            return;
          }

          if (eventName === "end") {
            log("[end]");
            return;
          }

          // Default: print raw.
          log(`[${eventName}] ${dataText}`);
        }

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const parts = buffer.split("\\n\\n");
          buffer = parts.pop() || "";
          for (const part of parts) {
            if (part.trim()) handleEventChunk(part);
          }
        }
        log("Stream finished.");
      }

      document.getElementById("startBtn").addEventListener("click", () => {
        start().catch((err) => log("Error: " + (err && err.message ? err.message : String(err))));
      });
    </script>
  </body>
</html>
"""


def create_agency(load_threads_callback=None, save_threads_callback=None) -> Agency:
    notion = HostedMCPTool(
        tool_config=Mcp(
            type="mcp",
            server_label="notion",
            server_url="https://mcp.notion.com/mcp",
            require_approval="never",
        )
    )

    agent = Agent(
        name="NotionHostedMCPAgent",
        instructions="You are a Notion assistant. Use MCP tools to search and summarize pages.",
        tools=[notion],
    )

    return Agency(
        agent,
        name="notion_hosted_mcp",
        load_threads_callback=load_threads_callback,
        save_threads_callback=save_threads_callback,
        oauth_token_path="./data/oauth-tokens",
    )


if __name__ == "__main__":
    oauth_registry = OAuthStateRegistry()
    app = run_fastapi(
        agencies={"notion_hosted_mcp": create_agency},
        host="0.0.0.0",
        port=PORT,
        return_app=True,
        oauth_registry=oauth_registry,
    )

    if app is None:
        raise SystemExit(1)

    @app.get("/demo/notion", response_class=HTMLResponse)
    async def demo_page() -> HTMLResponse:
        return HTMLResponse(DEMO_PAGE)

    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
