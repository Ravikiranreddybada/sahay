import type { Metadata } from "next";
import { Anek_Devanagari, Anek_Latin, Red_Hat_Mono } from "next/font/google";
import "./globals.css";

const anek = Anek_Latin({ subsets: ["latin"], axes: ["wdth"], variable: "--font-anek" });
const anekDeva = Anek_Devanagari({ subsets: ["devanagari"], axes: ["wdth"], variable: "--font-anek-deva" });
const mono = Red_Hat_Mono({ subsets: ["latin"], variable: "--font-mono" });

export const metadata: Metadata = {
  title: "Sahay Care Assistant",
  description: "Grounded healthcare care assistant: LangGraph + MCP + hybrid RAG + evals",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${anek.variable} ${anekDeva.variable} ${mono.variable}`}>
      <body>{children}</body>
    </html>
  );
}
