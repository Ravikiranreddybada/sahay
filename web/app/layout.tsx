import type { Metadata } from "next";
import { Geist, JetBrains_Mono, Noto_Sans_Devanagari } from "next/font/google";
import "./globals.css";

const sans = Geist({ subsets: ["latin"], variable: "--font-geist" });
const deva = Noto_Sans_Devanagari({ subsets: ["devanagari"], variable: "--font-deva" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono" });

export const metadata: Metadata = {
  title: "Sahay Care Assistant",
  description: "A grounded care assistant for family health, orders, claims, and care journeys.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${deva.variable} ${mono.variable}`}>
      <body>{children}</body>
    </html>
  );
}
