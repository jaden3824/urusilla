import type { Metadata } from 'next';
import Link from 'next/link';

const siteUrl = 'https://urusilla-language.pages.dev';
const repoUrl = 'https://github.com/jaden3824/urusilla';
const probeUrl = `${siteUrl}/language-probe.json`;
const accountingUrl = `${siteUrl}/agent-task.json`;
const validatorUrl = `${repoUrl}/blob/main/tools/validate_language_probe.py`;
const computeRunUrl = `${repoUrl}/issues/new?template=compute-run.yml`;
const counterexampleUrl = `${repoUrl}/issues/new?template=counterexample.yml`;

export const metadata: Metadata = {
  title: 'Reproduce Urusilla — one bounded result, no credentials',
  description:
    'A no-install reproduction guide for one Urusilla language probe or accounting check, with exact evidence fields and conservative claim boundaries.',
  alternates: {
    canonical: '/reproduce',
    types: {
      'text/markdown': '/reproduce.md',
    },
  },
  openGraph: {
    title: 'Reproduce one Urusilla result',
    description:
      'Choose one bounded public artifact, preserve the exact response, and report failures as faithfully as passes.',
    type: 'article',
    url: '/reproduce',
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
    title: 'Reproduce one Urusilla result',
    description:
      'One public artifact, one fresh receiver, no credentials, and an exact result record.',
    images: ['/og-language.png'],
  },
};

const structuredData = {
  '@context': 'https://schema.org',
  '@type': 'TechArticle',
  '@id': `${siteUrl}/reproduce#guide`,
  headline: 'Reproduce one Urusilla result',
  description:
    'A bounded, no-install guide for testing one public Urusilla artifact and returning an exact positive, negative, refusal, fallback, or malformed result.',
  url: `${siteUrl}/reproduce`,
  mainEntityOfPage: `${siteUrl}/reproduce`,
  dateModified: '2026-08-23',
  author: {
    '@type': 'Person',
    name: 'jaden3824',
    url: 'https://github.com/jaden3824',
  },
  publisher: {
    '@type': 'Person',
    name: 'jaden3824',
    url: 'https://github.com/jaden3824',
  },
  license: 'https://www.apache.org/licenses/LICENSE-2.0',
  isAccessibleForFree: true,
  about: [
    'AI agent communication',
    'semantic protocol evaluation',
    'reproducible agent benchmarks',
  ],
  hasPart: [
    {
      '@type': 'CreativeWork',
      name: 'One-fetch action-state language probe',
      url: probeUrl,
      encodingFormat: 'application/json',
    },
    {
      '@type': 'CreativeWork',
      name: '60-second accounting check',
      url: accountingUrl,
      encodingFormat: 'application/json',
    },
  ],
};

const responseFields = [
  'receiver model and exact version, when visible',
  'runtime or host',
  'prior exposure to Urusilla: yes, no, or unknown',
  'the exact raw response, unchanged',
  'PASS, SAFE_FALLBACK, FAIL, or not-run',
  'the first divergence or fallback reason',
];

export default function Reproduce() {
  return (
    <main className="reproduce-page">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify(structuredData).replace(/</g, '\\u003c'),
        }}
      />
      <a className="skip-link" href="#protocol">Skip to the reproduction paths</a>

      <nav className="nav shell" aria-label="Reproduction navigation">
        <Link className="wordmark" href="/" aria-label="Urusilla home">
          <span className="wordmark-mark" aria-hidden="true">U</span>
          <span>urusilla</span>
        </Link>
        <div className="nav-links">
          <a href="#protocol">Choose a path</a>
          <a href="#report">Report evidence</a>
          <a className="nav-cta" href={repoUrl}>Repository ↗</a>
        </div>
      </nav>

      <article>
        <header className="reproduce-hero shell">
          <p className="eyebrow"><span className="pulse" /> Independent results wanted</p>
          <h1>Reproduce one result.<br /><em>Keep the failure.</em></h1>
          <p className="hero-lede">
            Use one fresh receiver on one bounded public artifact. Preserve its
            exact answer—even when it refuses, falls back, or is malformed. You
            do not need to install Urusilla or disclose a credential.
          </p>
          <div className="hero-actions">
            <a className="button button-primary" href={probeUrl}>
              Open the one-fetch probe <span aria-hidden="true">→</span>
            </a>
            <a className="button button-secondary" href="#protocol">
              Compare the two paths <span aria-hidden="true">↓</span>
            </a>
          </div>
          <p className="reproduce-boundary">
            Current boundary: general unfamiliar-agent token saving remains 0%.
            One passing response is not adoption, conformance, authorization, or
            an efficiency result.
          </p>
        </header>

        <section className="reproduce-section shell" id="protocol">
          <div className="section-heading">
            <p className="section-index">01 / CHOOSE EXACTLY ONE PATH</p>
            <h2>Small enough to falsify.</h2>
          </div>
          <div className="reproduce-grid">
            <article className="reproduce-card featured-card">
              <span className="community-mode">LANGUAGE USE · ONE FETCH</span>
              <h3>Can the receiver preserve bounded typed meaning?</h3>
              <p>
                Give a fresh agent the self-contained action-state probe. It must
                preserve negation, failure, null, source ownership, hard
                constraints, uncertainty, and the absence of effect authority.
              </p>
              <dl>
                <div><dt>Install</dt><dd>None</dd></div>
                <div><dt>Network</dt><dd>One public GET</dd></div>
                <div><dt>Effects</dt><dd>Forbidden</dd></div>
                <div><dt>Result</dt><dd>One canonical JSON object</dd></div>
              </dl>
              <a className="text-link" href={probeUrl}>Open language-probe.json →</a>
            </article>

            <article className="reproduce-card">
              <span className="community-mode">ACCOUNTING · ABOUT 60 SECONDS</span>
              <h3>Can unknown failed-attempt usage be counted as zero?</h3>
              <p>
                Read the hosted task and return only decision, reason,
                participant, and runtime. The correct record keeps unknown usage
                unknown and performs no action.
              </p>
              <dl>
                <div><dt>Install</dt><dd>None</dd></div>
                <div><dt>Network</dt><dd>One public GET</dd></div>
                <div><dt>Effects</dt><dd>Forbidden</dd></div>
                <div><dt>Result</dt><dd>Four exact fields</dd></div>
              </dl>
              <a className="text-link" href={accountingUrl}>Open agent-task.json →</a>
            </article>
          </div>
        </section>

        <section className="reproduce-section reproduce-dark" id="report">
          <div className="shell reproduce-report">
            <div>
              <p className="section-index">02 / PRESERVE THE OBSERVATION</p>
              <h2>Report what happened,<br />not what should have happened.</h2>
              <p>
                Raw output is the primary observation. Do not repair formatting,
                hide a refusal, infer an unavailable model version, or turn a
                missing token count into zero.
              </p>
            </div>
            <div className="evidence-list" aria-label="Minimum evidence fields">
              {responseFields.map((field, index) => (
                <div key={field}>
                  <span>{String(index + 1).padStart(2, '0')}</span>
                  <p>{field}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="reproduce-section shell">
          <div className="section-heading">
            <p className="section-index">03 / VALIDATE LOCALLY</p>
            <h2>Your credential stays with you.</h2>
          </div>
          <div className="direct-answer">
            <p>
              For the language probe, save the exact response outside the
              checkout and run the dependency-free validator from a repository
              snapshot:
            </p>
            <code className="command-block">python3 tools/validate_language_probe.py RESPONSE.json</code>
            <p>
              <code>PASS</code>, <code>SAFE_FALLBACK</code>, and <code>FAIL</code>{' '}
              are distinct observations. If you do not run the validator,
              report <code>not-run</code>; do not guess.
            </p>
            <a className="text-link" href={validatorUrl}>Inspect the validator source →</a>
          </div>
        </section>

        <section className="reproduce-section shell reproduce-faq">
          <div className="section-heading">
            <p className="section-index">04 / DIRECT ANSWERS</p>
            <h2>What this does—and does not—show.</h2>
          </div>
          <div className="faq-grid">
            <article><h3>Do I need an API key?</h3><p>No. Use a runtime you already control. Never send Urusilla a credential, billing identifier, or private prompt.</p></article>
            <article><h3>Are refusals useful?</h3><p>Yes. Refusal, fallback, malformed output, null, and failure are valid observations when preserved exactly.</p></article>
            <article><h3>Does reading imply adoption?</h3><p>No. Reading, cloning, starring, or answering a project-operated request is not independent adoption.</p></article>
            <article><h3>Does one pass prove efficiency?</h3><p>No. It does not measure complete task tokens against concise language and JSON baselines.</p></article>
          </div>
        </section>

        <section className="final-cta shell">
          <p className="eyebrow">Publication is a separate choice.</p>
          <h2>Return the exact result.<br />Let evidence change the project.</h2>
          <div className="hero-actions">
            <a className="button button-primary" href={computeRunUrl}>
              Submit a reviewed run <span aria-hidden="true">↗</span>
            </a>
            <a className="button button-secondary light" href={counterexampleUrl}>
              Report a counterexample <span aria-hidden="true">↗</span>
            </a>
          </div>
          <p className="microcopy">
            Posting requires your own authority. This page does not upload a
            result, contact another person, or grant publication permission.
          </p>
        </section>
      </article>

      <footer className="footer shell">
        <span>Urusilla · reproducibility before reach · urusilla-site-2026-08-28.2</span>
        <Link href="/">Return to the research overview →</Link>
      </footer>
    </main>
  );
}
