// src/app/api/copilotkit/route.ts
import { NextRequest } from "next/server";

const AG_UI_BACKEND_URL = process.env.NEXT_PUBLIC_AG_UI_BACKEND_URL || "";

export const POST = async (req: NextRequest) => {
  const body = await req.json();

  if (body.method === "info") {
    // Return agent info
    return new Response(JSON.stringify({
      "version": "0.0.31",
      "agents": {
        "myAgent": {
          "name": "myAgent",
          "description": "",
          "className": "st"
        }
      },
      "audioFileTranscriptionEnabled": false
    }), {
      headers: { "Content-Type": "application/json" },
    });
  }


  if (body.method === "agent/run") {
    const agentId = body.params?.agentId;
    if (agentId !== "myAgent") {
      return new Response(JSON.stringify({
        type: "RUN_ERROR",
        message: `Agent '${agentId}' not found`,
        code: "AGENT_NOT_FOUND"
      }), {
        headers: { "Content-Type": "application/json" },
      });
    }

    // Forward the request to the AG-UI backend
    const aguiPayload = {
      thread_id: body.body.threadId,
      run_id: body.body.runId,
      state: body.body.state,
      messages: body.body.messages,
      tools: body.body.tools || [],
      context: body.body.context || [],
      forwardedProps: body.body.forwardedProps,
      additional_instructions: body.body.additional_instructions,
    };

    try {
      const response = await fetch(AG_UI_BACKEND_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(aguiPayload),
      });

      if (!response.ok) {
        return new Response(JSON.stringify({
          type: "RUN_ERROR",
          message: `Backend error: ${response.status}`,
          code: "BACKEND_ERROR"
        }), {
          headers: { "Content-Type": "application/json" },
        });
      }

      // Return the streaming response directly
      return new Response(response.body, {
        headers: {
          "Content-Type": "text/event-stream",
          "Cache-Control": "no-cache",
          "Connection": "keep-alive",
        },
      });
    } catch (error) {
      return new Response(JSON.stringify({
        type: "RUN_ERROR",
        message: `Network error: ${error}`,
        code: "NETWORK_ERROR"
      }), {
        headers: { "Content-Type": "application/json" },
      });
    }
  }

  return new Response(JSON.stringify({
    type: "RUN_ERROR",
    message: `Unsupported method: ${body.method}`,
    code: "UNSUPPORTED_METHOD"
  }), {
    headers: { "Content-Type": "application/json" },
  });
};
