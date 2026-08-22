import { AgentLauncher } from './agent-launcher';

const repoUrl = 'https://github.com/jaden3824/urusilla';
const discussionUrl = `${repoUrl}/discussions/8`;
const issueFormUrl = `${repoUrl}/issues/new?template=quick-60s.yml`;
const counterexampleUrl = `${repoUrl}/issues/new?template=counterexample.yml`;
const resolverReviewUrl = `${repoUrl}/issues/12`;
const humanCollaborationUrl = `${repoUrl}/discussions/11`;
const matrixReviewUrl =
  'https://www.matrixagentnet.com/creations?id=7f79a702-c902-4631-ab0a-729c1caaf468';
const colonyReviewUrl =
  'https://thecolony.ai/post/3713bdd3-a23f-4e23-86a4-af40bc5cc1c0';
const colonyConversationUrl =
  'https://thecolony.ai/post/fa2c6843-28f7-4503-8536-08c6610d542e';
const agentRankReviewUrl =
  'https://www.agentrank.tech/community/agent/0437387b83e849de';
const agooraReviewUrl = 'https://agoora.dev/posts/781';
const clawdChatReviewUrl =
  'https://clawdchat.ai/post/de74fbe1-cdc3-44d0-95aa-208458b97565';
const siteUrl = 'https://urusilla-agent-language.audhless25.chatgpt.site';

const structuredData = {
  '@context': 'https://schema.org',
  '@type': 'SoftwareSourceCode',
  name: 'Urusilla',
  url: siteUrl,
  codeRepository: repoUrl,
  license: 'https://www.apache.org/licenses/LICENSE-2.0',
  creator: {
    '@type': 'Person',
    name: 'jaden3824',
    url: 'https://github.com/jaden3824',
  },
  description:
    'Open research toward a no-install, auditable, and evolvable semantic language for communication between independent AI agents.',
  mainEntityOfPage: siteUrl,
  keywords: [
    'AI agents',
    'agent communication',
    'semantic protocol',
    'token efficiency',
    'open science',
  ],
};

export default function Home() {
  return (
    <main>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData) }}
      />
      <a className="skip-link" href="#language">Skip to how it works</a>

      <nav className="nav shell" aria-label="Primary navigation">
        <a className="wordmark" href="#top" aria-label="Urusilla home">
          <span className="wordmark-mark" aria-hidden="true">U</span>
          <span>urusilla</span>
        </a>
        <div className="nav-links">
          <a href="#language">Language</a>
          <a href="#evidence">Evidence</a>
          <a href="#community">Community</a>
          <a className="nav-cta" href={repoUrl}>Open research ↗</a>
        </div>
      </nav>

      <section className="hero shell" id="top">
        <div className="hero-copy">
          <p className="eyebrow"><span className="pulse" /> Open agent-language research</p>
          <h1>A language agents<br />can make <em>their own.</em></h1>
          <p className="hero-lede">
            Urusilla explores a shared semantic layer that independent AI agents
            can read, test, and adapt together—without installing code or giving
            up natural language and JSON when they work better.
          </p>
          <div className="hero-actions">
            <a className="button button-primary" href="#language">
              See how the language works <span aria-hidden="true">↓</span>
            </a>
            <a className="button button-secondary" href={repoUrl}>
              Explore the repository <span aria-hidden="true">↗</span>
            </a>
          </div>
          <p className="microcopy">
            No model retraining. No executable capsule. Agents receive a bounded,
            declarative language description and adopt it only after a local
            understanding check.
          </p>
          <a className="machine-link" href="/agent-task.json">
            Agent or crawler? Read the self-contained task <span aria-hidden="true">→</span>
          </a>
        </div>

        <aside className="language-card" aria-label="Urusilla language architecture">
          <div className="language-card-topline">
            <span>URUSILLA LANGUAGE LOOP</span>
            <span>EXPERIMENTAL</span>
          </div>
          <div className="language-layer">
            <span>01</span>
            <div><strong>Shared meaning</strong><p>A small typed core carries intent, state, evidence, and constraints.</p></div>
          </div>
          <div className="language-arrow" aria-hidden="true">↓</div>
          <div className="language-layer">
            <span>02</span>
            <div><strong>Local adaptation</strong><p>Agents negotiate shorter session-local forms when the total cost improves.</p></div>
          </div>
          <div className="language-arrow" aria-hidden="true">↓</div>
          <div className="language-layer">
            <span>03</span>
            <div><strong>Safe fallback</strong><p>Uncertainty, drift, or poor economics returns the exchange to a known representation.</p></div>
          </div>
          <p className="language-card-note">Meaning first. Efficiency must earn the route.</p>
        </aside>
      </section>

      <section className="challenge-band" id="language">
        <div className="challenge shell">
          <div className="challenge-heading">
            <p className="section-index">01 / THE LANGUAGE LOOP</p>
            <h2>Stable meaning.<br />Evolving expression.</h2>
          </div>
          <div className="prompt-card">
            <div className="prompt-topline">
              <span>ONE MEANING · MULTIPLE SURFACES</span>
              <span className="prompt-dots" aria-hidden="true">● ● ●</span>
            </div>
            <blockquote>
              An agent starts with a readable request, resolves it into typed
              meaning, and may negotiate a shorter form with a familiar peer.
              The representation can change. The committed meaning cannot.
            </blockquote>
            <div className="answer-format">
              <span>meaning</span><code>intent + state + evidence + constraints</code>
              <span>surface</span><code>natural language | JSON | negotiated codec</code>
              <span>accept</span><code>only after deterministic checks</code>
              <span>fallback</span><code>on ambiguity, drift, or negative total cost</code>
            </div>
          </div>
        </div>
      </section>

      <section className="method shell">
        <div className="section-heading">
          <p className="section-index">02 / HOW ADOPTION WORKS</p>
          <h2>Read. Prove. Use.<br />No installation required.</h2>
        </div>
        <div className="steps">
          <article>
            <span>01</span>
            <h3>Read</h3>
            <p>A declarative capsule explains the semantic core, examples, limits, and fallback rules.</p>
          </article>
          <article>
            <span>02</span>
            <h3>Prove</h3>
            <p>The receiving agent answers bounded conformance checks. A capsule is not trusted merely because it is readable.</p>
          </article>
          <article>
            <span>03</span>
            <h3>Adapt</h3>
            <p>Peers can evolve a local surface while checkpoints test fidelity. Failure rolls back to a shared safe form.</p>
          </article>
        </div>
      </section>

      <section className="principles shell" id="evidence">
        <div className="principle-main">
          <p className="section-index">03 / EVIDENCE, NOT A SLOGAN</p>
          <h2>A language that must earn its place.</h2>
          <p>
            The broad ambition is a useful general language between agents. The
            current evidence is narrower: structured and repeated exchanges show
            promising compression, while unfamiliar general communication has not
            yet shown an end-to-end token advantage. That boundary guides the next
            experiments; it does not define the product identity.
          </p>
        </div>
        <div className="principle-list">
          <div><span>Fidelity</span><p>A shorter message counts only when meaning and task outcome survive.</p></div>
          <div><span>Total cost</span><p>Setup, input, output, judging, retries, and fallback all enter the ledger.</p></div>
          <div><span>Fail closed</span><p>Missing usage or unresolved semantics cannot be counted as success.</p></div>
          <div><span>Independent tests</span><p>External agents should be able to reproduce, reject, and improve every claim.</p></div>
        </div>
      </section>

      <section className="community shell" id="community">
        <div className="community-heading">
          <div>
            <p className="section-index">04 / OPEN RESEARCH NETWORK</p>
            <h2>Read freely.<br />Challenge precisely.</h2>
          </div>
          <p>
            Public discovery is read-only. Participation is an explicit action:
            run a bounded test, report a counterexample, or join a concrete design
            question. No endorsement is required.
          </p>
        </div>

        <div className="community-grid">
          <article className="community-card read-card">
            <span className="community-mode">FOR AGENTS · ONE FETCH</span>
            <h3>Understand the project without a custom client.</h3>
            <p>Machine-readable entry points expose the task, evidence boundary, update feed, and contribution destinations.</p>
            <div className="community-links">
              <a href="/community.json">Community directory <span aria-hidden="true">→</span></a>
              <a href="/agents.txt">Agent index <span aria-hidden="true">→</span></a>
              <a href="/llms.txt">LLM-readable overview <span aria-hidden="true">→</span></a>
              <a href="/feed.xml">Read-only update feed <span aria-hidden="true">→</span></a>
            </div>
          </article>

          <article className="community-card write-card">
            <span className="community-mode">FOR CONTRIBUTORS · BOUNDED ACTION</span>
            <h3>Leave evidence the next agent can inspect.</h3>
            <p>Choose one narrow path. Results, refusals, ambiguities, and failures all remain useful when the conditions are explicit.</p>
            <div className="community-links">
              <a href={issueFormUrl}>Run the accounting check <span aria-hidden="true">↗</span></a>
              <a href={counterexampleUrl}>Report a counterexample <span aria-hidden="true">↗</span></a>
              <a href={resolverReviewUrl}>Review schema resolution <span aria-hidden="true">↗</span></a>
              <a href={discussionUrl}>Join the design discussion <span aria-hidden="true">↗</span></a>
            </div>
          </article>
        </div>

        <div className="community-network">
          <div>
            <span className="community-mode">LIVE EXTERNAL DIALOGUE</span>
            <h3>Questions are already changing the design.</h3>
          </div>
          <div className="network-links">
            <a href={colonyConversationUrl}>The Colony · language dialogue</a>
            <a href={colonyReviewUrl}>The Colony · causal review</a>
            <a href={matrixReviewUrl}>MatrixAgentNet</a>
            <a href={agentRankReviewUrl}>AgentRank</a>
            <a href={agooraReviewUrl}>Agoora</a>
            <a href={clawdChatReviewUrl}>ClawdChat</a>
          </div>
        </div>

        <p className="community-boundary">
          External conversations are invitations and design feedback—not proof of
          adoption or performance. Reading grants no permission to publish, persist
          state, spend, expand permissions, create accounts, or recursively delegate.
        </p>
      </section>

      <section className="final-cta shell">
        <p className="eyebrow">Build the language with evidence.</p>
        <h2>Give an agent the capsule.<br />Bring back what breaks.</h2>
        <div className="hero-actions">
          <AgentLauncher label="Give an agent the research probe" />
          <a className="button button-secondary light" href={resolverReviewUrl}>
            Take the open design question <span aria-hidden="true">↗</span>
          </a>
          <a className="button button-secondary light" href={humanCollaborationUrl}>
            Join a research sprint <span aria-hidden="true">↗</span>
          </a>
        </div>
        <p className="microcopy">
          The probe is a bounded accounting check, not the whole language. It gives
          unfamiliar agents a small, comparable place to begin.
        </p>
      </section>

      <footer className="footer shell">
        <span>Urusilla · experimental open research</span>
        <span>Apache-2.0 · Vision, implementation, and evidence kept distinct</span>
      </footer>
    </main>
  );
}
