// src/app/api/copilotkit/route.ts
import { HttpAgent } from "@ag-ui/client";
import {
  CopilotRuntime,
  EmptyAdapter,
  copilotRuntimeNextJSAppRouterEndpoint
} from "@copilotkit/runtime";
import { NextRequest } from "next/server";

// Point this to your AG‑UI backend URL
const myAgent = new HttpAgent({ url: "http://localhost:8080/agency1/get_response_stream/" });

const runtime = new CopilotRuntime({ agents: { myAgent } });

export const POST = async (req: NextRequest) => {
  const { handleRequest } = copilotRuntimeNextJSAppRouterEndpoint({
    runtime,
    serviceAdapter: new EmptyAdapter(),
    endpoint: "/api/copilotkit",
  });
  return handleRequest(req);
};
