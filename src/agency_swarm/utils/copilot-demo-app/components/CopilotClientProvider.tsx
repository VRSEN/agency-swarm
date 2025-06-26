"use client";
import { CopilotKit } from "@copilotkit/react-core";
import { CopilotChat } from "@copilotkit/react-ui";

export default function CopilotClientProvider({ children }: { children: React.ReactNode }) {
  return (
    <CopilotKit
      agent="myAgent"
      runtimeUrl="/api/copilotkit"
      showDevConsole={false}
    >
      <CopilotChat
        instructions={"You are assisting the user as best as you can. Answer in the best way possible given the data you have."}
        labels={{
          title: "Your Assistant",
          initial: "Hello 👋, this is a demo preview of the CopilotKit and is still a work in progress. New features will be added soon.",
        }}
      />
      {children}
    </CopilotKit>
  );
} 