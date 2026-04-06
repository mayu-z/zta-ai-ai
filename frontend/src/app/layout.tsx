import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";

import { ToastHost } from "@/components/ui/toast-host";

import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

const jetBrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "ZTA-AI",
  description: "Zero Trust AI Gateway",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${jetBrainsMono.variable} h-full antialiased`}
    >
      <body className="min-h-full bg-background text-text-primary">
        {children}
        <ToastHost />
      </body>
    </html>
  );
}
