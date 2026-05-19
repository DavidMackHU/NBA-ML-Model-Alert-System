import { NextResponse } from "next/server";

export const runtime = "edge";

export async function GET(request: Request) {
  // Vercel sends Authorization: Bearer <CRON_SECRET> for all cron invocations.
  // Only enforce when CRON_SECRET is set so local curl testing still works.
  const secret = process.env.CRON_SECRET;
  if (secret) {
    const auth = request.headers.get("authorization");
    if (auth !== `Bearer ${secret}`) {
      return NextResponse.json({ ok: false }, { status: 401 });
    }
  }

  const backend =
    process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

  try {
    const res = await fetch(`${backend}/api/health`, {
      signal: AbortSignal.timeout(8_000),
    });
    return NextResponse.json({ ok: res.ok, status: res.status });
  } catch (err) {
    return NextResponse.json({ ok: false, error: String(err) }, { status: 503 });
  }
}
