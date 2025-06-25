"use client";
import { CopilotSidebar } from "@copilotkit/react-ui";

export default function ChatUI() {
  return (
    <CopilotSidebar
      defaultOpen={true}
      labels={{
        title: "Assistant",
        initial: "Hi! How can I help?",
      }}
    />
  );
}
