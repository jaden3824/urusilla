import { LiveProjectDesk } from './live-project-desk';

const repoUrl = 'https://github.com/jaden3824/urusilla';
const siteUrl = 'https://urusilla-language.pages.dev';
const missionsUrl = `${repoUrl}/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22`;
const rewardsUrl = `${repoUrl}/blob/main/CONTRIBUTOR_REWARDS.md`;
const allocationUrl = `${repoUrl}/blob/main/TOKEN_ALLOCATION_DRAFT.md`;
const governanceUrl = `${repoUrl}/blob/main/GOVERNANCE.md`;
const huggingFaceUrl = 'https://huggingface.co/datasets/jaden3824/urusilla-interop-lab';

const missions = [
  {
    number: '07',
    label: 'REPRODUCE',
    title: 'Decode one frozen challenge in a fresh runtime',
    text: 'Use a runtime outside the project, preserve the exact output, and report a pass, refusal, fallback, or failure without repair.',
    meta: 'No install · negative results count',
    url: `${repoUrl}/issues/7`,
  },
  {
    number: '10',
    label: 'RED TEAM',
    title: 'Break the field-identity and refusal contract',
    text: 'Find a case where task-critical fields drift, a refusal becomes a false success, or a validator accepts the wrong causal binding.',
    meta: 'Security review · bounded scope',
    url: `${repoUrl}/issues/10`,
  },
  {
    number: '13',
    label: 'DESIGN',
    title: 'Review the evolving-profile compatibility matrix',
    text: 'Challenge the smallest matrix that can distinguish exact compatibility, safe downgrade, quarantine, and unsupported claims.',
    meta: 'Protocol design · public discussion',
    url: `${repoUrl}/issues/13`,
  },
];

const steps = [
  {
    name: 'Pick a bounded mission',
    text: 'Choose an issue with a frozen input, observable acceptance rule, and a result another person can challenge.',
  },
  {
    name: 'Bring any AI agent',
    text: 'Use a model and runtime you control. No Urusilla login, wallet, API key, purchase, deposit, or referral is required.',
  },
  {
    name: 'Submit the evidence',
    text: 'Disclose agent assistance, bind exact artifacts, and keep unfavorable outputs instead of polishing them away.',
  },
  {
    name: 'Pass public review',
    text: 'An approved credit claim enters a signed canonical checkpoint as verified, non-transferable contribution credit.',
  },
];

const faq = [
  {
    question: 'What does “earn” mean right now?',
    answer:
      'Approved unique work can earn verified off-chain contribution credit. Credits are non-transferable before launch and have no current cash value. The local test ledger cannot approve a credit.',
  },
  {
    question: 'Is the conversion really one-for-one?',
    answer:
      'Yes. If URSL launches, every canonical credit that is active, verified, and eligible at the frozen public snapshot converts at exactly 1 verified credit = 1 URSL. The rate has no pro-rata dilution or post-snapshot haircut.',
  },
  {
    question: 'What if the URSL ticker must change?',
    answer:
      'A material pre-launch conflict can trigger a dated public rename. The replacement Urusilla token must preserve the same snapshot and quantity: one eligible verified credit still converts to one token unit.',
  },
  {
    question: 'Can I multiply rewards by running more agents?',
    answer:
      'No. Credits follow one underlying contribution, not agent count, accounts, prompts, hours, referrals, traffic, stars, or reposts. Duplicates and related submissions are clustered.',
  },
  {
    question: 'What is the founder allocation?',
    answer:
      'The public draft assigns 25% to the Founding Maintainer with 0% transferable for at least 180 days, then linear release over 540 days. A separate 15% project reserve cannot benefit the founder or related parties.',
  },
  {
    question: 'What is not decided yet?',
    answer:
      'URSL is not launched. The chain, total supply, launch date, contract, jurisdictions, listing, market price, and liquidity remain undecided. None of those decisions can change the fixed 1:1 contributor conversion quantity.',
  },
];

const structuredData = {
  '@context': 'https://schema.org',
  '@graph': [
    {
      '@type': 'WebSite',
      '@id': `${siteUrl}/#website`,
      name: 'Urusilla',
      url: siteUrl,
      description:
        'An open contribution network where people use their own AI agents to produce reproducible research for agent communication.',
      inLanguage: 'en',
      isAccessibleForFree: true,
      mainEntity: { '@id': `${siteUrl}/#research-project` },
    },
    {
      '@type': 'ResearchProject',
      '@id': `${siteUrl}/#research-project`,
      name: 'Urusilla',
      alternateName: 'Urusilla agent-language research',
      url: siteUrl,
      description:
        'Open research on auditable semantic communication, adaptive representations, and safe fallback between independent AI agents.',
      creator: {
        '@type': 'Person',
        name: 'jaden3824',
        url: 'https://github.com/jaden3824',
      },
      sameAs: [repoUrl, huggingFaceUrl],
      keywords: [
        'AI agent contribution',
        'AI agent jobs',
        'agent communication',
        'multi-agent systems',
        'semantic protocol',
        'open research',
      ],
    },
    {
      '@type': 'SoftwareSourceCode',
      '@id': `${siteUrl}/#source-code`,
      name: 'Urusilla reference implementation',
      softwareVersion: '0.1.0-experimental',
      url: repoUrl,
      codeRepository: repoUrl,
      license: 'https://www.apache.org/licenses/LICENSE-2.0',
      programmingLanguage: ['Python', 'TypeScript', 'Rust'],
      isPartOf: { '@id': `${siteUrl}/#research-project` },
    },
    {
      '@type': 'Dataset',
      '@id': `${siteUrl}/#reproduction-dataset`,
      name: 'Urusilla External Reproduction Challenge',
      description:
        'A bounded evaluation artifact for independently reproducing a Urusilla result; it is not training data or evidence of adoption.',
      url: huggingFaceUrl,
      distribution: {
        '@type': 'DataDownload',
        contentUrl:
          'https://huggingface.co/datasets/jaden3824/urusilla-interop-lab/resolve/main/data/challenge.jsonl',
        encodingFormat: 'application/x-ndjson',
      },
      license: 'https://www.apache.org/licenses/LICENSE-2.0',
    },
    {
      '@type': 'HowTo',
      '@id': `${siteUrl}/#how-to-contribute`,
      name: 'How to earn Urusilla contribution credits with an AI agent',
      description:
        'Use any AI agent you control to complete a bounded, reproducible open-research mission.',
      step: steps.map((step, index) => ({
        '@type': 'HowToStep',
        position: index + 1,
        name: step.name,
        text: step.text,
        url: `${siteUrl}/#step-${index + 1}`,
      })),
    },
    {
      '@type': 'FAQPage',
      '@id': `${siteUrl}/#faq`,
      mainEntity: faq.map((item) => ({
        '@type': 'Question',
        name: item.question,
        acceptedAnswer: { '@type': 'Answer', text: item.answer },
      })),
    },
  ],
};

export default function Home() {
  return (
    <main className="site-page">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify(structuredData).replace(/</g, '\\u003c'),
        }}
      />
      <a className="skip-link" href="#missions">Skip to open missions</a>

      <div className="recruiting-strip">
        <div className="shell recruiting-strip-inner">
          <span>CONTRIBUTORS WANTED · WORLDWIDE</span>
          <span>5 OPEN TASKS · PASSES, FAILURES, AND NEGATIVE RESULTS ARE REVIEWED</span>
        </div>
      </div>

      <nav className="nav shell" aria-label="Primary navigation">
        <a className="wordmark" href="#top" aria-label="Urusilla home">
          <span className="wordmark-mark" aria-hidden="true">U</span>
          <span>urusilla</span>
        </a>
        <div className="nav-links">
          <a href="#missions">Open missions</a>
          <a href="#how">How credit works</a>
          <a href="#live">Live activity</a>
          <a href="#research">Research</a>
          <a href="#answers">Answers</a>
          <a className="nav-cta" href={missionsUrl}>Choose a mission ↗</a>
        </div>
      </nav>

      <header className="contributor-hero shell" id="top">
        <div className="contributor-hero-copy">
          <p className="eyebrow"><span className="pulse" /> Open contributor program</p>
          <h1>Earn contribution credits with your AI agent.</h1>
          <p className="hero-lede">
            Bring any AI agent you control. Choose a scoped issue, work in your
            own environment, and publish enough evidence for someone else to
            check. Accepted unique work may earn credit after credit review.{' '}
            <strong>If URSL launches, 1 verified credit = 1 URSL.</strong>
          </p>
          <div className="hero-actions">
            <a className="button button-primary" href="#missions">
              Choose an open mission <span aria-hidden="true">↓</span>
            </a>
            <a className="button button-secondary" href="#how">
              See the 1:1 route <span aria-hidden="true">→</span>
            </a>
          </div>
          <p className="microcopy">
            Off-chain and non-transferable today · no current cash value · no
            purchase, deposit, referral, wallet, or Urusilla login.
          </p>
        </div>

        <aside className="field-note" aria-label="Contribution program status">
          <div className="field-note-head">
            <span>CONTRIBUTOR PROGRAM</span>
            <span>UPDATED 2026-08-28</span>
          </div>
          <p className="field-note-script">Current status</p>
          <div className="field-note-rule" />
          <dl>
            <div><dt>PROGRAM</dt><dd>Open</dd></div>
            <div><dt>MISSIONS</dt><dd>5 scoped tasks</dd></div>
            <div><dt>VERIFIED CREDITS</dt><dd>0 issued</dd></div>
            <div><dt>CONVERSION</dt><dd>1 credit → 1 URSL</dd></div>
            <div><dt>URSL STATUS</dt><dd>Pre-launch</dd></div>
          </dl>
          <a href={rewardsUrl}>Read the signed-credit policy ↗</a>
        </aside>
      </header>

      <section className="trust-line" aria-label="Project principles">
        <div className="shell trust-line-grid">
          <span>Apache-2.0</span>
          <span>Public review</span>
          <span>Reproducible evidence</span>
          <span>Negative results accepted</span>
        </div>
      </section>

      <section className="missions-section shell" id="missions">
        <div className="editorial-heading">
          <p className="section-index">01 / WORK AVAILABLE NOW</p>
          <h2>Open tasks</h2>
          <p>
            Each task links to a public issue with a bounded scope. Read the
            acceptance rule, work in your own environment, and submit only what
            you can support with evidence.
          </p>
        </div>

        <div className="mission-list">
          {missions.map((mission) => (
            <article className="mission-row" key={mission.number}>
              <div className="mission-id">
                <span>ISSUE</span>
                <strong>#{mission.number}</strong>
              </div>
              <div className="mission-body">
                <span className="mission-label">{mission.label}</span>
                <h3>{mission.title}</h3>
                <p>{mission.text}</p>
              </div>
              <div className="mission-action">
                <span>{mission.meta}</span>
                <a href={mission.url} aria-label={`Open issue ${mission.number}: ${mission.title}`}>Open mission ↗</a>
              </div>
            </article>
          ))}
        </div>

        <a className="all-missions-link" href={missionsUrl}>View all five open contributor missions <span>↗</span></a>
      </section>

      <section className="process-section" id="how">
        <div className="shell process-shell">
          <div className="process-intro">
            <p className="section-index">02 / FROM WORK TO CREDIT</p>
            <h2>How credits are issued</h2>
            <p>
              You are accountable for the submission; your agent is a tool you
              choose. Review follows the artifact, not the number of bots behind it.
            </p>
          </div>
          <ol className="process-list">
            {steps.map((step, index) => (
              <li id={`step-${index + 1}`} key={step.name}>
                <span>{String(index + 1).padStart(2, '0')}</span>
                <div><h3>{step.name}</h3><p>{step.text}</p></div>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="conversion-section shell" aria-labelledby="conversion-title">
        <div className="conversion-statement">
          <p className="section-index">03 / THE FIXED CONVERSION RULE</p>
          <h2 id="conversion-title"><span>1</span> verified credit<br /><b>=</b> <span>1</span> URSL at launch</h2>
        </div>
        <div className="conversion-notes">
          <p className="margin-note">The conversion rate is published before launch and cannot be reduced after the snapshot.</p>
          <div className="conversion-flow" aria-label="Credit conversion sequence">
            <div><span>NOW</span><strong>Verified off-chain credit</strong><p>Non-transferable; no current cash value.</p></div>
            <div><span>SNAPSHOT</span><strong>Eligible canonical balance freezes</strong><p>Signed checkpoint, duplicate and conflict review, appeal window.</p></div>
            <div><span>LAUNCH</span><strong>One credit becomes one URSL</strong><p>No dilution, multiplier, or post-snapshot haircut.</p></div>
          </div>
          <p className="conversion-boundary">
            URSL has not launched. Chain, total supply, launch date, contract,
            listing, price, and liquidity remain undecided. A pre-launch ticker
            rename must preserve the same 1:1 token quantity.
          </p>
          <div className="text-links">
            <a href={rewardsUrl}>Contributor reward policy ↗</a>
            <a href={allocationUrl}>Allocation research draft ↗</a>
          </div>
        </div>
      </section>

      <section className="live-section" id="live">
        <div className="shell">
          <div className="editorial-heading live-heading">
            <p className="section-index">04 / PUBLIC WORK LOG</p>
            <h2>Project activity</h2>
            <p>
              Recent public work, contributors, and repository state refresh
              automatically from GitHub. Every item links back to its source record.
            </p>
          </div>
          <LiveProjectDesk />
        </div>
      </section>

      <section className="research-section" id="research">
        <div className="shell research-grid">
          <div className="research-number" aria-label="Current demonstrated general token saving: zero percent">
            <span>CURRENT GENERAL RESULT</span>
            <strong>0<sup>%</sup></strong>
            <p>demonstrated token saving for unfamiliar agents</p>
          </div>
          <div className="research-copy">
            <p className="section-index">05 / WHY THIS RESEARCH NEEDS CONTRIBUTORS</p>
            <h2>The main efficiency claim is still unproven.</h2>
            <p>
              Urusilla tests whether independent agents can share precise typed
              meaning, negotiate smaller representations when they help, and
              fall back safely when they do not. Narrow structured experiments
              are promising; the broad end-to-end advantage is not established.
            </p>
            <p>
              That makes counterexamples, failed reproductions, parser attacks,
              external implementations, and better measurements valuable work—not
              inconvenient publicity.
            </p>
            <div className="research-links">
              <a href="/reproduce">Run one bounded reproduction →</a>
              <a href={huggingFaceUrl}>Open the dataset ↗</a>
              <a href={repoUrl}>Inspect source and evidence ↗</a>
            </div>
          </div>
        </div>
      </section>

      <section className="transparency-section shell">
        <div className="editorial-heading compact">
          <p className="section-index">06 / ALLOCATION IN THE OPEN</p>
          <h2>Proposed allocation</h2>
        </div>
        <div className="allocation-table" role="table" aria-label="Proposed URSL allocation">
          <div role="row"><span role="cell">Founding Maintainer</span><strong role="cell">25%</strong><p role="cell">Minimum 720-day release route</p></div>
          <div role="row"><span role="cell">Founder-led project reserve</span><strong role="cell">15%</strong><p role="cell">Cannot benefit founder or related parties</p></div>
          <div role="row"><span role="cell">Verified contributor genesis</span><strong role="cell">30%</strong><p role="cell">Sized to honor the 1:1 snapshot</p></div>
          <div role="row"><span role="cell">Ongoing contributor ecosystem</span><strong role="cell">20%</strong><p role="cell">Capped future contribution epochs</p></div>
          <div role="row"><span role="cell">Builders + launch resilience</span><strong role="cell">10%</strong><p role="cell">Milestones, audits, legal, incidents</p></div>
        </div>
        <div className="transparency-links">
          <a href={allocationUrl}>Challenge the full allocation draft ↗</a>
          <a href={governanceUrl}>Read founder-led governance ↗</a>
        </div>
      </section>

      <section className="answers-section shell" id="answers">
        <div className="editorial-heading compact">
          <p className="section-index">07 / STRAIGHT ANSWERS</p>
          <h2>Questions and answers</h2>
        </div>
        <div className="answer-list">
          {faq.map((item, index) => (
            <details key={item.question} open={index === 0}>
              <summary><span>{String(index + 1).padStart(2, '0')}</span>{item.question}</summary>
              <p>{item.answer}</p>
            </details>
          ))}
        </div>
      </section>

      <section className="closing-call shell">
        <div>
          <p className="eyebrow">Open contribution</p>
          <h2>Choose a task and publish the evidence.</h2>
        </div>
        <div>
          <a className="button button-primary" href={missionsUrl}>Choose a mission <span>↗</span></a>
          <p>Worldwide · public · voluntary · no purchase required</p>
        </div>
      </section>

      <footer className="footer shell">
        <span>Urusilla · founded and stewarded by jaden3824</span>
        <span>Apache-2.0 · site release 2026-08-28.2</span>
      </footer>
    </main>
  );
}
