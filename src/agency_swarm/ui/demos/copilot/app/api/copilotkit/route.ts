// src/app/api/copilotkit/route.ts
import { HttpAgent } from "@ag-ui/client";
import {
  CopilotRuntime,
  EmptyAdapter,
  copilotRuntimeNextJSAppRouterEndpoint
} from "@copilotkit/runtime";
import { NextRequest } from "next/server";

// Read from environment variable, fallback to default if not set
const AG_UI_BACKEND_URL = process.env.NEXT_PUBLIC_AG_UI_BACKEND_URL || "";

const myAgent = new HttpAgent({ url: AG_UI_BACKEND_URL });

const runtime = new CopilotRuntime({ agents: { myAgent } });

export const POST = async (req: NextRequest) => {
  const { handleRequest } = copilotRuntimeNextJSAppRouterEndpoint({
    runtime,
    serviceAdapter: new EmptyAdapter(),
    endpoint: "/api/copilotkit",
  });
  return handleRequest(req);
};
