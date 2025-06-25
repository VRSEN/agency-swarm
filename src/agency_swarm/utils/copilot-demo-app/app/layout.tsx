import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import "@copilotkit/react-ui/styles.css";
import "@copilotkit/react-ui/styles.css";
import { CopilotKit } from "@copilotkit/react-core";
import { CopilotChat } from "@copilotkit/react-ui";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Your App Title",
  description: "Your app description",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body>
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
      </body>
    </html>
  );
}
