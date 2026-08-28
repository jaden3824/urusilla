import type { Metadata } from 'next';
import Link from 'next/link';

const siteUrl = 'https://urusilla-language.pages.dev';
const pageUrl = `${siteUrl}/earn-with-ai-agents`;
const repoUrl = 'https://github.com/jaden3824/urusilla';
const goodFirstIssueUrl = `${repoUrl}/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22`;
const computeRunUrl = `${repoUrl}/issues/new?template=compute-run.yml`;
const rewardPolicyUrl = `${repoUrl}/blob/main/CONTRIBUTOR_REWARDS.md`;
const allocationDraftUrl = `${repoUrl}/blob/main/TOKEN_ALLOCATION_DRAFT.md`;
const contributionGuideUrl = `${repoUrl}/blob/main/CONTRIBUTING.md`;

export const metadata: Metadata = {
  title: 'Earn With AI Agents: Contribution Credits | Urusilla',
  description:
    'Use your own AI agent to complete reproducible open-research tasks and earn verified contribution credit after review. If URSL launches, 1 verified eligible snapshot credit = 1 URSL.',
  alternates: { canonical: '/earn-with-ai-agents' },
  openGraph: {
    title: 'Earn contribution credits with your AI agent',
    description:
      'Bring any AI agent and complete verifiable work. If URSL launches, 1 verified eligible snapshot credit = 1 URSL.',
    type: 'website',
    url: '/earn-with-ai-agents',
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

const steps = [
  {
    name: 'Choose one bounded task',
    text: 'Start with an open issue, frozen reproduction, counterexample, implementation, security review, or documentation task.',
  },
  {
    name: 'Use your own AI agent',
    text: 'Work in an environment you control. Urusilla does not request your API key, private prompt, or a new site account.',
  },
  {
    name: 'Submit reproducible evidence',
    text: 'Bind the result to exact artifacts, disclose agent assistance, and preserve failures, refusals, and negative results.',
  },
  {
    name: 'Earn reviewed credit',
    text: 'Accepted unique work may receive whole-number, non-transferable off-chain credit after a separate published, non-conflicted credit review. The local ledger alone cannot approve it.',
  },
];

const faq = [
  {
    question: 'Can I make money with an AI agent here today?',
    answer:
      'Urusilla does not currently pay cash and URSL has not launched. Approved unique work can earn non-transferable contribution credit after published review. If URSL launches, eligible verified snapshot credits convert one-for-one; no current price, listing, or cash value exists.',
  },
  {
    question: 'Do I need to buy a token or pay to participate?',
    answer:
      'No. There is no token sale, mining payment, deposit, or referral requirement. You use tools and an AI agent that you already control.',
  },
  {
    question: 'Do I need an Urusilla login?',
    answer:
      'No separate Urusilla account is required. Public submissions currently use GitHub, which may require a GitHub account to post. The project does not store a password or private credential.',
  },
  {
    question: 'Will running more agents earn more credits?',
    answer:
      'No. Agent count, accounts, logins, time spent, referrals, traffic, and repeated submissions do not create impact. Only accepted, uniquely identifiable contribution evidence is credited.',
  },
  {
    question: 'How do credits convert to URSL?',
    answer:
      'If URSL launches, every canonical credit that is active, verified, and eligible at the frozen public snapshot converts at exactly 1 verified credit = 1 URSL. The rate has no pro-rata dilution or post-snapshot haircut. URSL itself is still pre-launch.',
  },
  {
    question: 'What is the proposed founder allocation?',
    answer:
      'The public research draft proposes 25% for the Founding Maintainer: 0% transferable for 180 days, followed by linear release over 540 days. A separate 15% founder-led ecosystem reserve would be project-purpose funds under public multisignature controls and could not benefit the founder or related parties.',
  },
  {
    question: 'What happens when an accepted result is later invalidated?',
    answer:
      'Corrections and revocations remain visible as new append-only records. Earlier history is not silently edited, and revoked credit cannot be transferred or used for project authority.',
  },
];

const structuredData = {
  '@context': 'https://schema.org',
  '@graph': [
    {
      '@type': 'WebPage',
      '@id': `${pageUrl}#page`,
      url: pageUrl,
      name: 'Earn With AI Agents: Urusilla Contribution Credits',
      description:
        'A contribution-first path for using an AI agent to produce verifiable open-research work and earn verified off-chain credit after review.',
      inLanguage: 'en',
      datePublished: '2026-08-28',
      dateModified: '2026-08-28',
      isPartOf: { '@id': `${siteUrl}/#website` },
      about: { '@id': `${siteUrl}/#research-project` },
      primaryImageOfPage: { '@id': `${pageUrl}#image` },
      breadcrumb: { '@id': `${pageUrl}#breadcrumb` },
    },
    {
      '@type': 'ImageObject',
      '@id': `${pageUrl}#image`,
      url: `${siteUrl}/og-earn.png`,
      width: 1671,
      height: 941,
      caption: 'Earn contribution credits with an AI agent; if URSL launches, one verified eligible snapshot credit equals one URSL',
    },
    {
      '@type': 'BreadcrumbList',
      '@id': `${pageUrl}#breadcrumb`,
      itemListElement: [
        {
          '@type': 'ListItem',
          position: 1,
          name: 'Urusilla',
          item: siteUrl,
        },
        {
          '@type': 'ListItem',
          position: 2,
          name: 'Earn with AI agents',
          item: pageUrl,
        },
      ],
    },
    {
      '@type': 'HowTo',
      '@id': `${pageUrl}#how-to`,
      name: 'How to earn Urusilla contribution credits with an AI agent',
      description:
        'Complete uniquely identifiable, verifiable open-research work with an AI agent you control.',
      step: steps.map((step, index) => ({
        '@type': 'HowToStep',
        position: index + 1,
        name: step.name,
        text: step.text,
        url: `${pageUrl}#step-${index + 1}`,
      })),
    },
    {
      '@type': 'FAQPage',
      '@id': `${pageUrl}#faq`,
      mainEntity: faq.map((item) => ({
        '@type': 'Question',
        name: item.question,
        acceptedAnswer: {
          '@type': 'Answer',
          text: item.answer,
        },
      })),
    },
  ],
};

export default function EarnWithAiAgents() {
  return (
    <main className="earn-page">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify(structuredData).replace(/</g, '\\u003c'),
        }}
      />
      <a className="skip-link" href="#how-it-works">Skip to how credits work</a>

      <nav className="nav shell" aria-label="Contributor navigation">
        <Link className="wordmark" href="/" aria-label="Urusilla home">
          <span className="wordmark-mark" aria-hidden="true">U</span>
          <span>urusilla</span>
        </Link>
        <div className="nav-links">
          <a href="#how-it-works">How it works</a>
          <a href="#eligible-work">Eligible work</a>
          <a href="#direct-answers">Direct answers</a>
          <a className="nav-cta" href={goodFirstIssueUrl}>Choose a task ↗</a>
        </div>
      </nav>

      <article>
        <header className="earn-hero shell">
          <div>
            <p className="eyebrow"><span className="pulse" /> AI agent contributor program</p>
            <h1>Earn contribution credit<br />with your <em>AI agent.</em></h1>
            <p className="hero-lede">
              Looking for a real way to make AI-agent work count? Bring any agent
              you control, complete verifiable open-research tasks, and build an
              early-contributor record through work that passes review.
            </p>
            <div className="hero-actions">
              <a className="button button-primary" href={goodFirstIssueUrl}>
                Choose a contribution task <span aria-hidden="true">↗</span>
              </a>
              <a className="button button-secondary" href={rewardPolicyUrl}>
                Read the credit policy <span aria-hidden="true">↗</span>
              </a>
            </div>
            <p className="microcopy">
              No Urusilla login, token purchase, deposit, or referral mining.
              GitHub may require an account only when you choose to publish a submission.
            </p>
          </div>

          <aside className="credit-summary" aria-label="Current contribution credit status">
            <span className="community-mode">CURRENT STATUS</span>
            <h2>Work first.<br />Credit after review.</h2>
            <dl>
              <div><dt>After approval</dt><dd>Off-chain contribution credit</dd></div>
              <div><dt>Transfer</dt><dd>Non-transferable</dd></div>
              <div><dt>Purchase required</dt><dd>None</dd></div>
              <div><dt>Evidence rule</dt><dd>Unique and reproducible</dd></div>
            </dl>
            <p>
              Credits have no current monetary value and are not cash, payment, or
              a token today. The local ledger prototype is not an approval. If URSL
              launches, eligible verified snapshot credits convert at exactly 1:1.
            </p>
          </aside>
        </header>

        <section className="earn-section earn-dark" id="how-it-works">
          <div className="shell">
            <div className="section-heading">
              <p className="section-index">01 / HOW IT WORKS</p>
              <h2>One accountable contributor.<br />Any agent you choose.</h2>
            </div>
            <div className="credit-steps">
              {steps.map((step, index) => (
                <article id={`step-${index + 1}`} key={step.name}>
                  <span>{String(index + 1).padStart(2, '0')}</span>
                  <h3>{step.name}</h3>
                  <p>{step.text}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="earn-section shell" id="eligible-work">
          <div className="section-heading">
            <p className="section-index">02 / WHAT EARNS CREDIT</p>
            <h2>Evidence that changes<br />what the project knows.</h2>
          </div>
          <div className="eligible-grid">
            <article>
              <span>REPRODUCE</span>
              <h3>Independent results</h3>
              <p>Run a frozen task, preserve exact outputs and usage, and report both passes and failures.</p>
              <a className="text-link" href="/reproduce">Open the reproduction guide →</a>
            </article>
            <article>
              <span>CHALLENGE</span>
              <h3>Counterexamples</h3>
              <p>Find semantic loss, unsafe fallback, accounting gaps, incompatibilities, or claims the evidence cannot support.</p>
              <a className="text-link" href={`${repoUrl}/issues/new?template=counterexample.yml`}>Report a counterexample ↗</a>
            </article>
            <article>
              <span>BUILD</span>
              <h3>Code and security</h3>
              <p>Improve runtimes, codecs, validators, test vectors, integrations, threat models, and fail-closed behavior.</p>
              <a className="text-link" href={goodFirstIssueUrl}>Browse scoped issues ↗</a>
            </article>
            <article>
              <span>EXPLAIN</span>
              <h3>Technical documentation</h3>
              <p>Make a tested concept, result, limitation, or reproduction path clearer across languages and runtimes.</p>
              <a className="text-link" href={contributionGuideUrl}>Read the contribution guide ↗</a>
            </article>
          </div>
        </section>

        <section className="earn-section earn-ledger">
          <div className="shell earn-ledger-grid">
            <div>
              <p className="section-index">03 / WHY BOT COUNT DOES NOT PAY</p>
              <h2>Impact is scarce.<br />Agent instances are not.</h2>
            </div>
            <div className="direct-answer compact-answer">
              <p>
                Credit follows the underlying contribution, not the number of
                agents, accounts, prompts, logins, hours, referrals, stars, or
                reposts used to produce it. Exact duplicates are rejected and
                related submissions can share one capped review cluster.
              </p>
              <p>
                Negative results remain eligible when they are reproducible and
                prevent a false claim or unsafe deployment. Purchased influence
                cannot change technical acceptance, evidence weight, or governance.
              </p>
              <a className="text-link" href={rewardPolicyUrl}>Inspect the full allocation policy ↗</a>
            </div>
          </div>
        </section>

        <section className="earn-section shell reproduce-faq" id="direct-answers">
          <div className="section-heading">
            <p className="section-index">04 / DIRECT ANSWERS</p>
            <h2>What “earn” means here.</h2>
          </div>
          <div className="faq-grid">
            {faq.map((item) => (
              <article key={item.question}>
                <h3>{item.question}</h3>
                <p>{item.answer}</p>
              </article>
            ))}
          </div>
          <p className="allocation-note">
            Review the proposed 25% founder allocation, 30% verified-contributor
            genesis pool, minimum 720-day founder release route, and reserve safeguards in the{' '}
            <a className="text-link" href={allocationDraftUrl}>public allocation research draft ↗</a>.
          </p>
        </section>

        <section className="final-cta shell">
          <p className="eyebrow">Bring your agent. Keep the evidence.</p>
          <h2>Start with one task<br />that another person can verify.</h2>
          <div className="hero-actions">
            <a className="button button-primary" href={goodFirstIssueUrl}>
              Choose a good first issue <span aria-hidden="true">↗</span>
            </a>
            <a className="button button-secondary light" href={computeRunUrl}>
              Submit one reviewed run <span aria-hidden="true">↗</span>
            </a>
            <a className="button button-secondary light" href={rewardPolicyUrl}>
              Read the reward policy <span aria-hidden="true">↗</span>
            </a>
          </div>
          <p className="microcopy">
            Submission is voluntary and public. Never provide a credential,
            billing identifier, private prompt, or proprietary data.
          </p>
        </section>
      </article>

      <footer className="footer shell">
        <span>Urusilla · contribution-first open research · urusilla-site-2026-08-28.2</span>
        <span>Apache-2.0 · No separate Urusilla account required</span>
      </footer>
    </main>
  );
}
