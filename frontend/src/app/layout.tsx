import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Redação Digital IA - Painel de Controle Autônomo",
  description: "Plataforma de inteligência artificial para monitoramento de notícias, checagem factual e distribuição multiplataforma.",
  icons: {
    icon: "/favicon.ico",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="pt-BR">
      <body className="antialiased bg-slate-950 text-slate-100 min-h-screen">
        {children}
      </body>
    </html>
  );
}
