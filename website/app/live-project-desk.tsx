'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';

const repoUrl = 'https://github.com/jaden3824/urusilla';
const liveActivityUrl = '/api/project-activity';
const snapshotUrl = '/project-activity.json';
const cacheKey = 'urusilla-public-project-activity-v1';
const refreshIntervalMs = 10 * 60_000;

type Repo = {
  stargazers_count: number;
  forks_count: number;
  open_issues_count: number;
  pushed_at: string;
  html_url: string;
};

type Actor = {
  login: string;
  avatar_url: string;
  html_url?: string;
};

type GithubEvent = {
  id: string;
  type: string;
  actor: Actor;
  created_at: string;
  payload: {
    action?: string;
    ref?: string;
    ref_type?: string;
    commits?: Array<{ sha: string; message: string }>;
    issue?: { number: number; title: string; html_url: string };
    pull_request?: { number: number; title: string; html_url: string };
    comment?: { html_url: string };
    forkee?: { html_url: string };
  };
};

type Contributor = Actor & {
  contributions: number;
};

type DeskData = {
  repo: Repo;
  events: GithubEvent[];
  contributors: Contributor[];
};

type DeskSnapshot = DeskData & {
  generated_at?: string;
};

type CachedDesk = {
  stored_at: string;
  data: DeskData;
};

type Activity = {
  id: string;
  actor: Actor;
  verb: string;
  subject: string;
  detail: string;
  url: string;
  createdAt: string;
};

function relativeTime(value: string) {
  const elapsed = Date.now() - new Date(value).getTime();
  if (elapsed < 60_000) return 'just now';
  if (elapsed < 3_600_000) return `${Math.floor(elapsed / 60_000)}m ago`;
  if (elapsed < 86_400_000) return `${Math.floor(elapsed / 3_600_000)}h ago`;
  return `${Math.floor(elapsed / 86_400_000)}d ago`;
}

function readCachedDesk(): CachedDesk | null {
  try {
    const value = window.localStorage.getItem(cacheKey);
    if (!value) return null;
    const parsed = JSON.parse(value) as CachedDesk;
    if (!parsed.stored_at || !parsed.data?.repo || !Array.isArray(parsed.data.events) || !Array.isArray(parsed.data.contributors)) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

function writeCachedDesk(data: DeskData, storedAt: Date) {
  try {
    window.localStorage.setItem(cacheKey, JSON.stringify({ stored_at: storedAt.toISOString(), data }));
  } catch {
    // The public feed still works when storage is disabled.
  }
}

function eventToActivity(event: GithubEvent): Activity | null {
  const base = {
    id: event.id,
    actor: event.actor,
    createdAt: event.created_at,
  };

  switch (event.type) {
    case 'PushEvent': {
      const commit = event.payload.commits?.at(-1);
      const count = event.payload.commits?.length ?? 0;
      return {
        ...base,
        verb: 'pushed',
        subject: count ? `${count} commit${count === 1 ? '' : 's'}` : 'a repository update',
        detail: commit?.message.split('\n')[0] ?? 'Updated the repository',
        url: commit ? `${repoUrl}/commit/${commit.sha}` : `${repoUrl}/commits`,
      };
    }
    case 'IssuesEvent':
      if (!event.payload.issue) return null;
      return {
        ...base,
        verb: event.payload.action ?? 'updated',
        subject: `issue #${event.payload.issue.number}`,
        detail: event.payload.issue.title,
        url: event.payload.issue.html_url,
      };
    case 'IssueCommentEvent':
      if (!event.payload.issue) return null;
      return {
        ...base,
        verb: 'commented on',
        subject: `issue #${event.payload.issue.number}`,
        detail: event.payload.issue.title,
        url: event.payload.comment?.html_url ?? event.payload.issue.html_url,
      };
    case 'PullRequestEvent':
    case 'PullRequestReviewEvent':
      if (!event.payload.pull_request) return null;
      return {
        ...base,
        verb: event.type === 'PullRequestReviewEvent' ? 'reviewed' : (event.payload.action ?? 'updated'),
        subject: `pull request #${event.payload.pull_request.number}`,
        detail: event.payload.pull_request.title,
        url: event.payload.pull_request.html_url,
      };
    case 'CreateEvent':
      return {
        ...base,
        verb: 'created',
        subject: `${event.payload.ref_type ?? 'repository item'}${event.payload.ref ? ` ${event.payload.ref}` : ''}`,
        detail: 'New public project record',
        url: repoUrl,
      };
    case 'WatchEvent':
      return {
        ...base,
        verb: 'starred',
        subject: 'the project',
        detail: 'Public interest signal',
        url: `${repoUrl}/stargazers`,
      };
    case 'ForkEvent':
      return {
        ...base,
        verb: 'forked',
        subject: 'the repository',
        detail: 'Started an independent project copy',
        url: event.payload.forkee?.html_url ?? `${repoUrl}/forks`,
      };
    default:
      return null;
  }
}

async function fetchJson<T>(url: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(url, {
    headers: { Accept: 'application/vnd.github+json' },
    signal,
  });
  if (!response.ok) throw new Error(`GitHub returned ${response.status}`);
  return response.json() as Promise<T>;
}

export function LiveProjectDesk() {
  const [data, setData] = useState<DeskData | null>(null);
  const [status, setStatus] = useState<'loading' | 'ready' | 'refreshing' | 'error'>('loading');
  const [checkedAt, setCheckedAt] = useState<Date | null>(null);

  const load = useCallback(async (manual = false) => {
    setStatus((current) => (manual && current === 'ready' ? 'refreshing' : current === 'ready' ? 'ready' : 'loading'));
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 10_000);
    try {
      const live = await fetchJson<DeskSnapshot>(liveActivityUrl, controller.signal);
      if (!live.repo || !Array.isArray(live.events) || !Array.isArray(live.contributors)) {
        throw new Error('Live activity response is incomplete');
      }
      const nextData = { repo: live.repo, events: live.events, contributors: live.contributors };
      const receivedAt = live.generated_at ? new Date(live.generated_at) : new Date();
      setData(nextData);
      setCheckedAt(receivedAt);
      writeCachedDesk(nextData, receivedAt);
      setStatus('ready');
    } catch {
      setStatus('error');
    } finally {
      window.clearTimeout(timeout);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    const initial = window.setTimeout(() => {
      void (async () => {
        const cached = readCachedDesk();
        const cachedAt = cached ? new Date(cached.stored_at) : null;
        const cacheIsFresh = Boolean(cachedAt && Date.now() - cachedAt.getTime() < refreshIntervalMs);

        if (cached && cachedAt && !cancelled) {
          setData(cached.data);
          setCheckedAt(cachedAt);
          setStatus('ready');
        } else {
          try {
            const response = await fetch(snapshotUrl, { cache: 'no-store' });
            if (!response.ok) throw new Error(`Snapshot returned ${response.status}`);
            const snapshot = await response.json() as DeskSnapshot;
            if (!cancelled) {
              setData({ repo: snapshot.repo, events: snapshot.events, contributors: snapshot.contributors });
              setCheckedAt(snapshot.generated_at ? new Date(snapshot.generated_at) : null);
              setStatus('ready');
            }
          } catch {
            if (!cancelled) setStatus('error');
          }
        }

        if (!cacheIsFresh && !cancelled) void load();
      })();
    }, 0);
    const interval = window.setInterval(() => void load(), refreshIntervalMs);
    return () => {
      cancelled = true;
      window.clearTimeout(initial);
      window.clearInterval(interval);
    };
  }, [load]);

  const activities = useMemo(
    () => data?.events.map(eventToActivity).filter((item): item is Activity => Boolean(item)).slice(0, 7) ?? [],
    [data],
  );

  return (
    <div className="live-desk" aria-busy={status === 'loading' || status === 'refreshing'}>
      <div className="live-desk-topline">
        <div className="live-status">
          <span className={status === 'error' ? 'live-dot error' : 'live-dot'} aria-hidden="true" />
          <strong>
            {status === 'error'
              ? data ? 'PUBLIC SNAPSHOT · LIVE REFRESH TEMPORARILY UNAVAILABLE' : 'SOURCE TEMPORARILY UNAVAILABLE'
              : status === 'loading' ? 'CONNECTING TO PUBLIC GITHUB RECORDS' : 'RECENT PUBLIC GITHUB RECORDS · AUTO-REFRESH ON'}
          </strong>
        </div>
        <div className="live-controls">
          <span aria-live="polite">
            {checkedAt ? `Checked ${checkedAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}` : 'Connecting…'}
          </span>
          <button type="button" onClick={() => void load(true)} disabled={status === 'refreshing'}>
            {status === 'refreshing' ? 'Refreshing…' : 'Refresh now'}
          </button>
        </div>
      </div>

      {status === 'error' && !data ? (
        <div className="live-error">
          <p>The public activity feed could not be reached. No project data is invented or cached as a substitute.</p>
          <a href={repoUrl}>Open the source repository ↗</a>
        </div>
      ) : (
        <>
          <div className="live-stats" aria-label="Current project statistics">
            <div><span>Stars</span><strong>{data?.repo.stargazers_count ?? '—'}</strong></div>
            <div><span>Forks</span><strong>{data?.repo.forks_count ?? '—'}</strong></div>
            <div><span>Open issues + PRs</span><strong>{data?.repo.open_issues_count ?? '—'}</strong></div>
            <div><span>Last repository push</span><strong>{data ? relativeTime(data.repo.pushed_at) : '—'}</strong></div>
          </div>

          <div className="live-desk-grid">
            <section className="activity-panel" aria-labelledby="activity-title">
              <div className="panel-heading">
                <h3 id="activity-title">Recent public work</h3>
                <a href={`${repoUrl}/activity`}>Full activity ↗</a>
              </div>
              <div className="activity-list">
                {activities.length ? activities.map((activity) => (
                  <a className="activity-item" href={activity.url} key={activity.id}>
                    {/* Public GitHub avatars are remote, user-specific, and intentionally left unoptimized. */}
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={activity.actor.avatar_url} alt="" width="36" height="36" loading="lazy" />
                    <div>
                      <p><strong>{activity.actor.login}</strong> {activity.verb} <span>{activity.subject}</span></p>
                      <small>{activity.detail}</small>
                    </div>
                    <time dateTime={activity.createdAt}>{relativeTime(activity.createdAt)}</time>
                  </a>
                )) : (
                  <p className="live-placeholder">Loading the latest public work…</p>
                )}
              </div>
            </section>

            <aside className="contributors-panel" aria-labelledby="contributors-title">
              <div className="panel-heading">
                <h3 id="contributors-title">Public contributors</h3>
                <a href={`${repoUrl}/graphs/contributors`}>Graph ↗</a>
              </div>
              <div className="contributor-list">
                {data?.contributors.slice(0, 8).map((contributor) => (
                  <a href={contributor.html_url ?? `${repoUrl}/commits?author=${contributor.login}`} key={contributor.login}>
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={contributor.avatar_url} alt="" width="42" height="42" loading="lazy" />
                    <span><strong>{contributor.login}</strong><small>{contributor.contributions} commit{contributor.contributions === 1 ? '' : 's'}</small></span>
                  </a>
                )) ?? <p className="live-placeholder">Loading contributors…</p>}
              </div>
              <p className="live-source-note">
                Public GitHub records only. The feed refreshes at most every 10 minutes,
                keeps the last public snapshot during rate limits, and may reflect GitHub publication delay.
                Credit status is never inferred from activity.
              </p>
            </aside>
          </div>
        </>
      )}
    </div>
  );
}
