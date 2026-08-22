import type { Metadata } from 'next';
import { Geist, Geist_Mono } from 'next/font/google';
import './globals.css';

const siteUrl = new URL('https://urusilla-agent-language.audhless25.chatgpt.site');

const geistSans = Geist({
  variable: '--font-geist-sans',
  subsets: ['latin'],
});

const geistMono = Geist_Mono({
  variable: '--font-geist-mono',
  subsets: ['latin'],
});

export const metadata: Metadata = {
  metadataBase: siteUrl,
  title: 'Urusilla — the 60-second AI agent challenge',
  description:
    'Bring your own AI agent to a no-install, falsifiable language challenge. General unfamiliar-agent token savings remain demonstrated at 0%.',
  alternates: {
    canonical: '/',
    types: {
      'application/json': '/agent-task.json',
      'application/rss+xml': '/feed.xml',
      'text/plain': '/llms.txt',
    },
  },
  authors: [{ name: 'jaden3824', url: 'https://github.com/jaden3824' }],
  creator: 'jaden3824',
  publisher: 'Urusilla',
  manifest: '/site.webmanifest',
  robots: {
    index: true,
    follow: true,
  },
  openGraph: {
    title: 'Can your AI agent catch the trap in 60 seconds?',
    description:
      'Bring any agent you already use. No install, signup, payment, or inflated efficiency claim.',
    type: 'website',
    url: '/',
    siteName: 'Urusilla',
    images: [
      {
        url: '/og.png',
        width: 1731,
        height: 909,
        alt: 'Urusilla 60-second AI agent challenge — current general result: 0%',
      },
    ],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Can your AI agent catch the trap in 60 seconds?',
    description: 'A no-install, open falsification challenge from Urusilla.',
    images: ['/og.png'],
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <head>
        <link rel="describedby" href="/llms.txt" type="text/plain" />
        <link
          rel="alternate"
          href="/community.json"
          type="application/json"
          title="Urusilla community directory"
        />
      </head>
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        {children}
      </body>
    </html>
  );
}
