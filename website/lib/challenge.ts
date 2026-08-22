import challenge from '../public/agent-challenge.json';
import discovery from '../public/.well-known/urusilla.json';

export const canonicalChallenge = challenge;
export const challengeIdentity = discovery.canonical_task;

export const challengePrompt = `${challenge.scenario}\n\n${challenge.question}`;

export const responseTemplate = [
  'decision: RETAIN | ROLLBACK',
  'reason: one public sentence',
  'participant: human | agent | human+agent',
  'runtime: none or exact agent/model/runtime identity if known',
].join('\n');
