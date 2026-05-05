const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET,OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

const IMPORTANCE_ORDER = { "高": 0, "中": 1, "低": 2 };
const IMPORTANCE_VALUES = new Set(["高", "中", "低"]);
const CONTENT_TYPE_VALUES = new Set(["traffic", "ffxiv"]);
const MAX_LIMIT = 100;

function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      ...CORS_HEADERS,
    },
  });
}

function errorResponse(message, status = 400) {
  return jsonResponse({ error: message }, status);
}

function parseLimit(value, defaultValue = 50) {
  if (!value) return defaultValue;
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || parsed < 1) return defaultValue;
  return Math.min(parsed, MAX_LIMIT);
}

function normalizeRow(row) {
  const analysis = row.analysis || {};
  return {
    week_id: row.week_id || "",
    title: row.title || "",
    link: row.link || "",
    source: row.source || "",
    published: row.published || "",
    created_at: row.created_at || "",
    content_type: row.content_type || "traffic",
    analysis: {
      importance: analysis.importance || "中",
      importance_reason: analysis.importance_reason || "",
      summary: analysis.summary || row.summary || "",
      analysis: analysis.analysis || "",
      tags: Array.isArray(analysis.tags) ? analysis.tags : [],
    },
  };
}

function compareArticle(a, b) {
  const orderA = IMPORTANCE_ORDER[a.analysis?.importance || "中"] ?? 1;
  const orderB = IMPORTANCE_ORDER[b.analysis?.importance || "中"] ?? 1;
  if (orderA !== orderB) return orderA - orderB;
  const ta = a.published ? new Date(a.published).getTime() : 0;
  const tb = b.published ? new Date(b.published).getTime() : 0;
  return ta - tb;
}

function aggregateWeeks(rows) {
  const bucket = new Map();
  for (const row of rows) {
    const weekId = row.week_id;
    if (!weekId) continue;
    const current = bucket.get(weekId) || {
      week_id: weekId,
      article_count: 0,
      high_count: 0,
    };
    current.article_count += 1;
    if ((row.analysis || {}).importance === "高") {
      current.high_count += 1;
    }
    bucket.set(weekId, current);
  }

  return Array.from(bucket.values()).sort((a, b) =>
    b.week_id.localeCompare(a.week_id),
  );
}

function aggregateTags(rows) {
  const aiTags = {};
  for (const row of rows) {
    const tags = (row.analysis || {}).tags;
    if (!Array.isArray(tags)) continue;
    for (const tag of tags) {
      if (!tag) continue;
      aiTags[tag] = (aiTags[tag] || 0) + 1;
    }
  }
  return {
    ai_tags: aiTags,
    user_tags: [],
  };
}

async function supabaseGet(env, path, searchParams) {
  const url = new URL(`${env.SUPABASE_URL}/rest/v1/${path}`);
  for (const [key, value] of searchParams.entries()) {
    url.searchParams.set(key, value);
  }

  const res = await fetch(url.toString(), {
    headers: {
      apikey: env.SUPABASE_SERVICE_ROLE_KEY,
      Authorization: `Bearer ${env.SUPABASE_SERVICE_ROLE_KEY}`,
    },
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Supabase query failed: ${res.status} ${body}`);
  }
  return res.json();
}

async function handleWeeks(env, url) {
  const params = new URLSearchParams();
  params.set("select", "week_id,analysis,content_type");
  params.set("order", "week_id.desc");
  const contentType = url.searchParams.get("content_type");
  if (contentType && CONTENT_TYPE_VALUES.has(contentType)) {
    params.set("content_type", `eq.${contentType}`);
  }
  const rows = await supabaseGet(env, "articles", params);
  return jsonResponse(aggregateWeeks(rows));
}

async function handleTags(env, url) {
  const params = new URLSearchParams();
  params.set("select", "analysis,content_type");
  const contentType = url.searchParams.get("content_type");
  if (contentType && CONTENT_TYPE_VALUES.has(contentType)) {
    params.set("content_type", `eq.${contentType}`);
  }
  const rows = await supabaseGet(env, "articles", params);
  return jsonResponse(aggregateTags(rows));
}

async function handleWeekDetail(env, weekId, url) {
  const params = new URLSearchParams();
  params.set(
    "select",
    "week_id,title,link,source,published,summary,analysis,content_type,created_at",
  );
  params.set("week_id", `eq.${weekId}`);
  params.set("order", "created_at.asc");
  const rows = await supabaseGet(env, "articles", params);
  let normalized = rows.map(normalizeRow);

  const contentType = url.searchParams.get("content_type");
  if (contentType && CONTENT_TYPE_VALUES.has(contentType)) {
    normalized = normalized.filter((article) => article.content_type === contentType);
  }

  const importance = url.searchParams.get("importance");
  if (importance && IMPORTANCE_VALUES.has(importance)) {
    normalized = normalized.filter(
      (article) => article.analysis.importance === importance,
    );
  }

  const tag = url.searchParams.get("tag");
  if (tag) {
    normalized = normalized.filter((article) => article.analysis.tags.includes(tag));
  }

  const q = (url.searchParams.get("q") || "").trim().toLowerCase();
  if (q) {
    normalized = normalized.filter((article) => {
      const content = [
        article.title,
        article.source,
        article.analysis.summary,
        article.analysis.analysis,
        ...article.analysis.tags,
      ]
        .join(" ")
        .toLowerCase();
      return content.includes(q);
    });
  }

  normalized.sort(compareArticle);
  const total = normalized.length;
  const limit = parseLimit(url.searchParams.get("limit"), 100);
  const offset = Math.max(0, Number.parseInt(url.searchParams.get("offset") || "0", 10) || 0);
  const paged = normalized.slice(offset, offset + limit);

  return jsonResponse({
    week_id: weekId,
    article_count: total,
    articles: paged,
  });
}

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") {
      return new Response(null, { headers: CORS_HEADERS });
    }

    if (!env.SUPABASE_URL || !env.SUPABASE_SERVICE_ROLE_KEY) {
      return errorResponse("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not configured", 500);
    }

    const url = new URL(request.url);
    const parts = url.pathname.replace(/\/+$/, "").split("/");

    try {
      if (request.method !== "GET") {
        return errorResponse("Method not allowed", 405);
      }

      if (url.pathname === "/api/weeks") {
        return await handleWeeks(env, url);
      }
      if (url.pathname === "/api/tags") {
        return await handleTags(env, url);
      }
      if (parts.length === 4 && parts[1] === "api" && parts[2] === "weeks") {
        const weekId = decodeURIComponent(parts[3]);
        return await handleWeekDetail(env, weekId, url);
      }

      return errorResponse("Not found", 404);
    } catch (error) {
      return errorResponse(error.message || "Internal error", 500);
    }
  },
};
