import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";

import { ToastProvider } from "@/components/ui/toast";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "Adaptive LMS — Intelligent Learning Platform",
    template: "%s · Adaptive LMS",
  },
  description:
    "Adaptive Learning Management System with live competency modelling, real-time adaptive sequencing, and grounded AI reporting.",
  keywords: [
    "LMS",
    "adaptive learning",
    "competency",
    "AI reporting",
    "education technology",
  ],
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#4f46e5",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${inter.variable} h-full antialiased`}>
      <body className="min-h-full bg-background font-sans text-fg">
        {/* Toasts are mounted at the root so any page can raise one without
            rendering its own container. */}
        <ToastProvider>{children}</ToastProvider>
      </body>
    </html>
  );
}
