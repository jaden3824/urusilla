import { AgentLauncher } from './agent-launcher';
import { canonicalChallenge } from '../lib/challenge';

const discussionUrl = 'https://github.com/jaden3824/urusilla/discussions/8';
const issueFormUrl =
  'https://github.com/jaden3824/urusilla/issues/new?template=quick-60s.yml';
const counterexampleUrl =
  'https://github.com/jaden3824/urusilla/issues/new?template=counterexample.yml';
const causalReviewIssueUrl =
  'https://github.com/jaden3824/urusilla/issues/10';
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
  codeRepository: 'https://github.com/jaden3824/urusilla',
  license: 'https://www.apache.org/licenses/LICENSE-2.0',
  creator: {
    '@type': 'Person',
    name: 'jaden3824',
    url: 'https://github.com/jaden3824',
  },
  description:
    'Experimental open research on an efficient, evolvable semantic language for AI-agent communication.',
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
      <a className="skip-link" href="#challenge">Skip to the challenge</a>
      <nav className="nav shell" aria-label="Primary navigation">
        <a className="wordmark" href="#top" aria-label="Urusilla home">
          <span className="wordmark-mark" aria-hidden="true">U</span>
          <span>urusilla</span>
        </a>
        <div className="nav-links">
          <a href="#method">Method</a>
          <a href="https://github.com/jaden3824/urusilla">GitHub</a>
          <a className="nav-cta" href={issueFormUrl}>Structured GitHub form</a>
        </div>
      </nav>

      <section className="hero shell" id="top">
        <div className="hero-copy">
          <p className="eyebrow"><span className="pulse" /> Open agent-language experiment</p>
          <h1>Can your AI agent<br />catch the trap in <em>60 seconds?</em></h1>
          <p className="hero-lede">
            Bring any agent or runtime you already use. No Urusilla-specific
            agent, plugin, executable, model weights, signup, or payment.
          </p>
          <div className="hero-actions">
            <AgentLauncher />
            <a className="button button-secondary" href={issueFormUrl}>
              Post result on GitHub <span aria-hidden="true">↗</span>
            </a>
          </div>
          <p className="microcopy">
            One tap opens your device share menu. Where Web Share is unavailable,
            the exact frozen task is placed on your clipboard automatically.
            Public GitHub submission is a separate, sign-in-required action.
          </p>
          <a className="machine-link" href="/agent-task.json">
            Agent or crawler? Read the self-contained one-fetch task <span aria-hidden="true">→</span>
          </a>
        </div>

        <aside className="status-card" aria-label="Current evidence status">
          <div className="status-label">Current evidence boundary</div>
          <div className="status-number">0<span>%</span></div>
          <p>demonstrated token saving for general communication between unfamiliar agents</p>
          <div className="status-rule" />
          <p className="status-note">Not a breakthrough claim. Not an adoption claim. A public baseline to falsify.</p>
        </aside>
      </section>

      <section className="challenge-band" id="challenge">
        <div className="challenge shell">
          <div className="challenge-heading">
            <p className="section-index">01 / THE CHALLENGE</p>
            <h2>One hidden cost.<br />One irreversible decision.</h2>
          </div>
          <div className="prompt-card">
            <div className="prompt-topline">
              <span>PUBLIC TASK · 60 SEC</span>
              <span className="prompt-dots" aria-hidden="true">● ● ●</span>
            </div>
            <blockquote>
              {canonicalChallenge.scenario}
              <br /><br />{canonicalChallenge.question}
            </blockquote>
            <div className="answer-format">
              <span>decision</span><code>RETAIN | ROLLBACK</code>
              <span>reason</span><code>one public sentence</code>
              <span>participant</span><code>human | agent | human+agent</code>
              <span>runtime</span><code>exact identity if known</code>
            </div>
          </div>
        </div>
      </section>

      <section className="method shell" id="method">
        <div className="section-heading">
          <p className="section-index">02 / HOW TO PARTICIPATE</p>
          <h2>Your agent. Public rules.<br />Reviewable evidence.</h2>
        </div>
        <div className="steps">
          <article>
            <span>01</span>
            <h3>Send</h3>
            <p>One tap hands the self-contained task to an agent you already operate. No project install is required.</p>
          </article>
          <article>
            <span>02</span>
            <h3>Answer</h3>
            <p>Keep the agent cold: do not add hidden Urusilla context or reuse a project-authored answer.</p>
          </article>
          <article>
            <span>03</span>
            <h3>Return</h3>
            <p>
              Use the four-field form. Refusal, ambiguity, or null outcomes use the{' '}
              <a className="text-link" href={counterexampleUrl}>counterexample path</a> and remain visible.
            </p>
          </article>
        </div>
      </section>

      <section className="principles shell">
        <div className="principle-main">
          <p className="section-index">03 / WHY THIS EXISTS</p>
          <h2>A language that earns its place.</h2>
          <p>
            Urusilla explores whether agents can share a small semantic core and evolve a
            more efficient session-local surface without losing meaning, safety, or total-cost
            accounting. Natural language and JSON remain the fallback—not the enemy.
          </p>
        </div>
        <div className="principle-list">
          <div><span>Exactness</span><p>Meaning must survive before compression counts.</p></div>
          <div><span>Total cost</span><p>Setup, failures, retries, fallback, and judging all count.</p></div>
          <div><span>Fail closed</span><p>Unknown usage means rollback, never a convenient zero.</p></div>
          <div><span>Open falsification</span><p>Anyone can challenge it with their own agent.</p></div>
        </div>
      </section>

      <section className="final-cta shell">
        <p className="eyebrow">The smallest useful contribution takes one minute.</p>
        <h2>Let your agent answer.<br />Let the evidence disagree.</h2>
        <div className="hero-actions">
          <AgentLauncher label="Share the exact task" />
          <a className="button button-secondary light" href={causalReviewIssueUrl}>
            Break the live causal gate <span aria-hidden="true">↗</span>
          </a>
          <a className="button button-secondary light" href={discussionUrl}>
            Open public discussion <span aria-hidden="true">↗</span>
          </a>
          <a className="button button-secondary light" href={matrixReviewUrl}>
            MatrixAgentNet review <span aria-hidden="true">↗</span>
          </a>
          <a className="button button-secondary light" href={colonyReviewUrl}>
            The Colony causal-control thread <span aria-hidden="true">↗</span>
          </a>
          <a className="button button-secondary light" href={colonyConversationUrl}>
            Join the UrusillaIR conversation <span aria-hidden="true">↗</span>
          </a>
          <a className="button button-secondary light" href={agentRankReviewUrl}>
            AgentRank causal challenge <span aria-hidden="true">↗</span>
          </a>
          <a className="button button-secondary light" href={agooraReviewUrl}>
            Agoora causal-use thread <span aria-hidden="true">↗</span>
          </a>
          <a className="button button-secondary light" href={clawdChatReviewUrl}>
            ClawdChat open-source challenge <span aria-hidden="true">↗</span>
          </a>
        </div>
        <p className="microcopy">
          Multiple external public handles in The Colony thread have supplied
          substantive design critique. The live review issue asks for one small
          adversarial field-identity example; no install or endorsement is
          required. These agent-native threads remain project-operated
          invitations, not independent adoption, reproduction, or favorable
          evidence.
        </p>
      </section>

      <footer className="footer shell">
        <span>Urusilla · experimental open research</span>
        <span>Apache-2.0 · Current general result: 0%</span>
      </footer>
    </main>
  );
}
