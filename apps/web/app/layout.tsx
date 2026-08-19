import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Signal — Music Intelligence",
  description: "Evidence-backed intelligence for artists, releases, labels, and trends.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
