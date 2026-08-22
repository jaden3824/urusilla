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
  title: 'Urusilla — a language agents can make their own',
  description:
    'Open research toward a no-install, auditable semantic language for independent AI agents, with typed meaning, adaptive codecs, safe fallback, and public evaluation.',
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
    title: 'A language agents can make their own',
    description:
      'Urusilla is open research on precise, efficient, and interoperable communication between independent AI agents.',
    type: 'website',
    url: '/',
    siteName: 'Urusilla',
    images: [
      {
        url: '/og-language.png',
        width: 1672,
        height: 941,
        alt: 'Urusilla — a language agents can make their own',
      },
    ],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Urusilla — a language agents can make their own',
    description:
      'Typed meaning, negotiated codecs, deterministic inspection, safe fallback, and open evaluation.',
    images: ['/og-language.png'],
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
          href="/language-probe.json"
          type="application/json"
          title="Urusilla one-fetch language-use probe"
        />
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
