import type { Metadata } from "next";
import { Fraunces, Manrope } from "next/font/google";

import "./globals.css";

const headingFont = Fraunces({
  subsets: ["latin"],
  weight: ["500", "600", "700"],
  variable: "--font-heading",
  preload: false,
});

const bodyFont = Manrope({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-body",
  preload: false,
});

export const metadata: Metadata = {
  title: "Gresham House | Response Workspace",
  description: "RFP/DDQ drafting workflow with retrieval and human approval.",
  icons: {
    icon: ["/api/client-config/assets/favicon.ico", "/favicon.ico"],
    shortcut: ["/api/client-config/assets/favicon.ico", "/favicon.ico"],
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${headingFont.variable} ${bodyFont.variable}`}>{children}</body>
    </html>
  );
}
