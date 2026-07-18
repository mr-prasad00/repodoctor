import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "RepoDoctor",
  description: "Run a bug report against real code before it reaches a maintainer.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
