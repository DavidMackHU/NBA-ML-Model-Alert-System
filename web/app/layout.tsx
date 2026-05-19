import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { NavLinks } from "./components/NavLinks";
import { ReactQueryProvider } from "./components/ReactQueryProvider";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3000"),
  title: "NBA +EV Alert System",
  description:
    "Live NBA market edge detection — candidate edges, CLV tracking, and honest backtest analysis.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.className} min-h-screen bg-zinc-950 text-zinc-100`}>
        <header className="sticky top-0 z-50 border-b border-zinc-800 bg-zinc-900/80 backdrop-blur-sm">
          <div className="mx-auto flex h-14 max-w-5xl items-center justify-between px-4">
            <a
              href="/"
              className="flex items-center gap-2 font-semibold tracking-tight text-zinc-100 hover:text-white"
            >
              <span className="h-2 w-2 rounded-full bg-emerald-500" />
              NBA +EV
            </a>
            <NavLinks />
          </div>
        </header>
        <ReactQueryProvider>
          <main className="mx-auto max-w-5xl px-4 py-6">{children}</main>
        </ReactQueryProvider>
      </body>
    </html>
  );
}
