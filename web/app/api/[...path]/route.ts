// Same-origin proxy to the FastAPI backend: no CORS in the browser, SSE passes through untouched.
const BACKEND = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

async function proxy(req: Request, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  const url = new URL(req.url);
  const target = `${BACKEND}/${path.join("/")}${url.search}`;
  // forward only what the backend needs: content type and credentials (never cookies/hosts)
  const headers: Record<string, string> = { "content-type": req.headers.get("content-type") ?? "application/json" };
  for (const h of ["authorization", "x-ops-key"]) {
    const v = req.headers.get(h);
    if (v) headers[h] = v;
  }
  const init: RequestInit = {
    method: req.method,
    headers,
    body: req.method === "GET" || req.method === "DELETE" ? undefined : await req.text(),
    cache: "no-store",
  };
  try {
    const res = await fetch(target, init);
    return new Response(res.body, {
      status: res.status,
      headers: {
        "content-type": res.headers.get("content-type") ?? "application/json",
        "cache-control": "no-cache",
        ...(res.headers.get("retry-after") ? { "retry-after": res.headers.get("retry-after")! } : {}),
      },
    });
  } catch {
    return Response.json({ detail: "Backend is not reachable. Start it with: uvicorn sahay.main:app --port 8000" }, { status: 502 });
  }
}

export const GET = proxy;
export const POST = proxy;
export const DELETE = proxy;
export const dynamic = "force-dynamic";
export const maxDuration = 60;
