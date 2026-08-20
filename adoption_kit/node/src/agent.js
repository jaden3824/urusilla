#!/usr/bin/env node
'use strict';

// Local stdin/stdout JSONL bridge. It never opens a socket or authorizes effects.
const readline = require('node:readline');
const kit = require('./index.js');

function capabilityFor(request) {
  return kit.createCapabilities({
    sourceId: request.source_id,
    cachedArtifacts: request.cached_artifacts || [],
  });
}

function handle(request) {
  if (!request || typeof request !== 'object' || Array.isArray(request)) {
    throw new kit.IntegrationError('request must be a JSON object', 'JSONL');
  }
  if (request.op === 'discover') {
    return capabilityFor(request);
  }
  if (request.op === 'decode') {
    return kit.decodeDelivery(request.delivery, {
      capability: capabilityFor(request),
      session: request.session,
      expectedSourceId: request.expected_source_id,
    });
  }
  if (request.op === 'encode') {
    return kit.encodeDelivery(request.message, {
      capability: capabilityFor(request),
      peerCapability: request.peer_capability,
      requestedMode: request.requested_mode || 'bridge',
      preferredRepresentation: request.preferred_representation,
    });
  }
  throw new kit.IntegrationError('unknown JSONL operation', 'JSONL');
}

const lines = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
lines.on('line', (line) => {
  let output;
  try {
    const request = kit.decodeJsonLine(`${line}\n`);
    output = { ok: true, result: handle(request) };
  } catch (exception) {
    output = {
      ok: false,
      error: {
        code: typeof exception.code === 'string' ? exception.code : 'INTEGRATION_ERROR',
        message: typeof exception.message === 'string' ? exception.message : 'rejected',
      },
    };
  }
  process.stdout.write(kit.encodeJsonLine(output));
});
