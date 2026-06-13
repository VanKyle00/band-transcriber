import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const maxDuration = 60;

// Proxy job submission to the Modal `web` endpoint. Keeps the Modal URL server-side
// and avoids browser CORS. The multipart FormData (file or url + stems) is forwarded as-is.
export async function POST(req: NextRequest) {
  const base = process.env.MODAL_WEB_URL;
  if (!base) {
    return NextResponse.json({ error: "MODAL_WEB_URL is not configured" }, { status: 500 });
  }
  const form = await req.formData();
  const res = await fetch(`${base}/jobs`, { method: "POST", body: form });
  const body = await res.text();
  if (!res.ok) {
    return NextResponse.json({ error: body || "submission failed" }, { status: 502 });
  }
  return new NextResponse(body, {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}
