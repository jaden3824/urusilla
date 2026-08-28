const githubApiBase = 'https://api.github.com/repos/jaden3824/urusilla';
const cacheSeconds = 10 * 60;

type JsonObject = Record<string, unknown>;

type Actor = {
  login: string;
  avatar_url: string;
  html_url: string;
};

type CommitRecord = {
  sha: string;
  message: string;
  created_at: string;
  actor: Actor;
};

export const dynamic = 'force-dynamic';

function isObject(value: unknown): value is JsonObject {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function nonNegativeInteger(value: unknown, field: string): number {
  if (!Number.isInteger(value) || (value as number) < 0) {
    throw new Error(`GitHub field ${field} is not a non-negative integer`);
  }
  return value as number;
}

function nonEmptyString(value: unknown, field: string): string {
  if (typeof value !== 'string' || !value) {
    throw new Error(`GitHub field ${field} is not non-empty text`);
  }
  return value;
}

function actorFrom(value: unknown, fallback: Actor): Actor {
  if (!isObject(value)) return fallback;
  const login = typeof value.login === 'string' && value.login ? value.login : fallback.login;
  const avatarUrl = typeof value.avatar_url === 'string' && value.avatar_url
    ? value.avatar_url
    : fallback.avatar_url;
  const htmlUrl = typeof value.html_url === 'string' && value.html_url
    ? value.html_url
    : fallback.html_url;
  return { login, avatar_url: avatarUrl, html_url: htmlUrl };
}

function normalizeCommit(value: unknown, fallbackActor: Actor): CommitRecord | null {
  if (!isObject(value) || !isObject(value.commit)) return null;
  const sha = typeof value.sha === 'string' ? value.sha : '';
  const message = typeof value.commit.message === 'string' ? value.commit.message : '';
  const author = isObject(value.commit.author) ? value.commit.author : null;
  const createdAt = author && typeof author.date === 'string' ? author.date : '';
  if (!sha || !message || !createdAt || Number.isNaN(Date.parse(createdAt))) return null;
  return {
    sha,
    message,
    created_at: createdAt,
    actor: actorFrom(value.author, fallbackActor),
  };
}

async function githubJson(path: string): Promise<unknown> {
  const response = await fetch(`${githubApiBase}${path}`, {
    headers: {
      Accept: 'application/vnd.github+json',
      'User-Agent': 'urusilla-language-public-activity',
      'X-GitHub-Api-Version': '2022-11-28',
    },
    cache: 'no-store',
  });
  if (!response.ok) throw new Error(`GitHub returned ${response.status}`);
  return response.json();
}

function jsonResponse(value: unknown, status = 200): Response {
  return Response.json(value, {
    status,
    headers: {
      'Access-Control-Allow-Origin': '*',
      'Cache-Control': status === 200
        ? `public, max-age=${cacheSeconds}, stale-while-revalidate=3600`
        : 'no-store',
      'X-Content-Type-Options': 'nosniff',
    },
  });
}

export async function GET(request: Request) {
  const cacheKey = new Request(new URL('/api/project-activity', request.url), {
    method: 'GET',
  });
  const edgeCache = typeof caches === 'undefined' ? null : caches.default;
  if (edgeCache) {
    try {
      const cached = await edgeCache.match(cacheKey);
      if (cached) {
        return new Response(cached.body, {
          status: cached.status,
          statusText: cached.statusText,
          headers: new Headers(cached.headers),
        });
      }
    } catch {
      // A cache failure must not hide otherwise available public GitHub data.
    }
  }

  try {
    const [repoValue, eventValue, contributorValue, commitValue] = await Promise.all([
      githubJson(''),
      githubJson('/events?per_page=30'),
      githubJson('/contributors?per_page=12'),
      githubJson('/commits?sha=main&per_page=10'),
    ]);
    if (!isObject(repoValue) || !Array.isArray(eventValue)
      || !Array.isArray(contributorValue) || !Array.isArray(commitValue)) {
      throw new Error('GitHub response shape is incomplete');
    }

    const fallbackActor: Actor = {
      login: 'jaden3824',
      avatar_url: 'https://github.com/jaden3824.png?size=96',
      html_url: 'https://github.com/jaden3824',
    };
    const owner = actorFrom(repoValue.owner, fallbackActor);
    const commits = commitValue
      .map((commit) => normalizeCommit(commit, owner))
      .filter((commit): commit is CommitRecord => commit !== null);
    const commitEvents = commits.map((commit) => ({
      id: `commit-${commit.sha}`,
      type: 'PushEvent',
      actor: commit.actor,
      created_at: commit.created_at,
      payload: {
        ref: 'refs/heads/main',
        commits: [{ sha: commit.sha, message: commit.message }],
      },
    }));
    const nonPushEvents = eventValue.filter(
      (event) => isObject(event) && event.type !== 'PushEvent',
    );
    const events = [...commitEvents, ...nonPushEvents]
      .sort((left, right) => {
        const leftTime = typeof left.created_at === 'string' ? Date.parse(left.created_at) : 0;
        const rightTime = typeof right.created_at === 'string' ? Date.parse(right.created_at) : 0;
        return rightTime - leftTime;
      })
      .slice(0, 30);
    const contributors = contributorValue.slice(0, 12).map((contributor, index) => {
      if (!isObject(contributor)) {
        throw new Error(`GitHub contributor ${index} is not an object`);
      }
      return {
        ...actorFrom(contributor, fallbackActor),
        contributions: nonNegativeInteger(
          contributor.contributions,
          `contributors[${index}].contributions`,
        ),
      };
    });

    const payload = {
      schema_version: 'urusilla-public-project-activity/1',
      generated_at: new Date().toISOString(),
      source: githubApiBase,
      repo: {
        stargazers_count: nonNegativeInteger(repoValue.stargazers_count, 'stargazers_count'),
        forks_count: nonNegativeInteger(repoValue.forks_count, 'forks_count'),
        open_issues_count: nonNegativeInteger(repoValue.open_issues_count, 'open_issues_count'),
        pushed_at: nonEmptyString(repoValue.pushed_at, 'pushed_at'),
        html_url: nonEmptyString(repoValue.html_url, 'html_url'),
      },
      events,
      contributors,
    };
    const response = jsonResponse(payload);
    if (edgeCache) {
      try {
        await edgeCache.put(cacheKey, response.clone());
      } catch {
        // Return the live response even when this edge cannot retain it.
      }
    }
    return response;
  } catch {
    return jsonResponse({
      schema_version: 'urusilla-public-project-activity/1',
      status: 'source-unavailable',
    }, 503);
  }
}
