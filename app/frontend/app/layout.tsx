import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Devoteam Reference Intelligence",
  description: "Find approved Devoteam experience and prepare proposal-ready reference presentations.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
