import type { Metadata } from 'next';
import { Barlow, Barlow_Condensed, IBM_Plex_Mono } from 'next/font/google';
import './globals.css';

/*
  Three roles, two families. Barlow and Barlow Condensed share a skeleton, so
  the structural labels and the player names read as one voice at two widths;
  Plex Mono grounds the numbers. Weights are kept deliberately few -- this is a
  page you load once and then stare at, but it still loads over a phone
  tether at a draft party.
*/

// Structural voice: the rail, headings, position chips, column labels.
const barlowCondensed = Barlow_Condensed({
  variable: '--font-barlow-condensed',
  subsets: ['latin'],
  weight: ['500', '600', '700'],
});

// Reading voice: player names and prose.
const barlow = Barlow({
  variable: '--font-barlow',
  subsets: ['latin'],
  weight: ['400', '600'],
});

// Data voice: ADP, VORP, VONA, byes, pick numbers -- anything compared down a column.
const plexMono = IBM_Plex_Mono({
  variable: '--font-plex-mono',
  subsets: ['latin'],
  weight: ['400', '500'],
});

export const metadata: Metadata = {
  title: 'Ground Game',
  description: 'A value-based fantasy football draft board. Shows what waiting costs you.',
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${barlowCondensed.variable} ${barlow.variable} ${plexMono.variable} antialiased`}
      >
        {children}
      </body>
    </html>
  );
}
