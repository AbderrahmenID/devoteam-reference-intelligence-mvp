import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Devoteam Reference Finder",
  description: "Multilingual, evidence-backed Devoteam reference retrieval",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
