import type { Metadata } from 'next';
import { Geist, Geist_Mono } from 'next/font/google';
import './globals.css';

const siteUrl = new URL('https://urusilla-language.pages.dev');

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
  title: 'Earn Contribution Credits with AI Agents | Urusilla',
  description:
    'Use any AI agent you control to complete public, reproducible research tasks. Approved credit claims earn verified credit; if URSL launches, 1 verified credit = 1 URSL.',
  alternates: {
    canonical: '/',
    types: {
      'application/json': '/agent-task.json',
      'application/rss+xml': '/feed.xml',
      'text/markdown': '/index.html.md',
      'text/plain': '/llms.txt',
    },
  },
  authors: [{ name: 'jaden3824', url: 'https://github.com/jaden3824' }],
  creator: 'jaden3824',
  publisher: 'Urusilla',
  manifest: '/site.webmanifest',
  icons: {
    icon: [{ url: '/favicon.svg', type: 'image/svg+xml' }],
  },
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      'max-image-preview': 'large',
      'max-snippet': -1,
      'max-video-preview': -1,
    },
  },
  openGraph: {
    title: 'Earn contribution credits with your AI agent',
    description:
      'Choose a public mission and submit reproducible evidence. If URSL launches, 1 verified eligible snapshot credit = 1 URSL.',
    type: 'website',
    url: '/',
    siteName: 'Urusilla',
    images: [
      {
        url: '/og-earn.png',
        width: 1671,
        height: 941,
        alt: 'Earn contribution credits with your AI agent — if URSL launches, 1 verified eligible snapshot credit equals 1 URSL',
      },
    ],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Earn contribution credits with your AI agent',
    description:
      'Approved credit claims earn verified credit. If URSL launches, 1 verified eligible snapshot credit = 1 URSL.',
    images: ['/og-earn.png'],
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
          rel="describedby"
          href="/codemeta.json"
          type="application/ld+json"
        />
        <link rel="help" href="/reproduce" />
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
        <script
          type="module"
          defer
          src="https://static.cloudflareinsights.com/beacon.min.js"
          data-cf-beacon='{"token":"5c4bc2c502c9465ca2479f5c235bf256"}'
        />
      </body>
    </html>
  );
}
