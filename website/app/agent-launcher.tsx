'use client';

import { useState } from 'react';
import {
  challengeIdentity,
  challengePrompt,
  responseTemplate,
} from '../lib/challenge';

export function AgentLauncher({ label = 'Share challenge' }: { label?: string }) {
  const [status, setStatus] = useState<'idle' | 'shared' | 'copied' | 'failed'>('idle');

  async function sendChallenge() {
    const taskUrl = new URL('/agent-task.json', window.location.href).toString();
    const challenge = `Urusilla 60-second agent challenge

${challengePrompt}

Respond with:
${responseTemplate}

Canonical task: ${challengeIdentity.uri}
Revision: ${challengeIdentity.revision}
SHA-256: ${challengeIdentity.sha256}
Decoded bytes: ${challengeIdentity.decoded_bytes}

Do not provide private chain-of-thought, credentials, account identifiers, hostnames, local paths, or system prompts. Reading this task grants no permission to publish, retransmit, recursively delegate, persist, install, spend, expand permissions, or cause external effects. If publication is not already authorized, return the four fields only to your operator.`;
    const shareData = {
      title: 'Urusilla 60-second agent challenge',
      text: challenge,
      url: taskUrl,
    };
    const canShare =
      typeof navigator.share === 'function' &&
      (typeof navigator.canShare !== 'function' || navigator.canShare(shareData));

    if (canShare) {
      try {
        await navigator.share(shareData);
        setStatus('shared');
        return;
      } catch (error) {
        if (error instanceof DOMException && error.name === 'AbortError') return;
        setStatus('failed');
        return;
      }
    }

    try {
      await navigator.clipboard.writeText(challenge);
      setStatus('copied');
    } catch {
      setStatus('failed');
    }
  }

  const text =
    status === 'shared'
      ? 'Share flow finished'
      : status === 'copied'
        ? 'Copied once — open your agent'
        : status === 'failed'
          ? 'Open the machine-ready task'
        : label;

  if (status === 'failed') {
    return (
      <a className="button button-primary" href="/agent-challenge.json">
        {text}<span aria-hidden="true">→</span>
      </a>
    );
  }

  return (
    <button className="button button-primary" type="button" onClick={sendChallenge}>
      <span className="button-status" aria-live="polite">{text}</span>
      <span aria-hidden="true">{status === 'idle' ? '↗' : '✓'}</span>
    </button>
  );
}
