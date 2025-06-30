import "./globals.css";
import { ReactNode } from "react";
import { CopilotKit } from "@copilotkit/react-core"; 
 
export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body> 
        {/* Make sure to use the URL you configured in the previous step  */}
        <CopilotKit runtimeUrl="/api/copilotkit"> 
          {children}
        </CopilotKit>
      </body>
    </html>
  );
}