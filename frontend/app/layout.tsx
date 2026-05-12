import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Tech0 Search",
  description: "New business idea analysis prototype",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ja">
      <body>{children}</body>
    </html>
  );
}
