import { ChatKit, useChatKit } from "@openai/chatkit-react";

// ChatKit connects to our Agency Swarm backend via the Vite proxy
const CHATKIT_API_URL = "/chatkit";
const CHATKIT_API_DOMAIN_KEY = "domain_pk_localhost_dev";

export function ChatKitPanel() {
  const chatkit = useChatKit({
    api: {
      url: CHATKIT_API_URL,
      domainKey: CHATKIT_API_DOMAIN_KEY,
    },
    theme: {
      colorScheme: "dark",
      radius: "round",
      density: "normal",
    },
    composer: {
      attachments: { enabled: false },
      placeholder: "Type a message...",
    },
    startScreen: {
      greeting: "Welcome to Agency Swarm",
      prompts: [
        {
          icon: "circle-question",
          label: "Say hello",
          prompt: "Hello! What can you help me with?",
        },
        {
          icon: "bolt",
          label: "Test calculation",
          prompt: "What is 15 * 7?",
        },
        {
          icon: "user",
          label: "Greet me",
          prompt: "Please greet me, my name is User",
        },
      ],
    },
  });

  return (
    <div className="relative pb-8 flex h-[90vh] w-full rounded-2xl flex-col overflow-hidden shadow-sm transition-colors">
      <ChatKit control={chatkit.control} className="block h-full w-full" />
    </div>
  );
}
