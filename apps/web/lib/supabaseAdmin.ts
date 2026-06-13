import { createClient, type SupabaseClient } from "@supabase/supabase-js";

// Lazily created server-only client (service role). Lazy init keeps `next build`
// working without env vars and avoids creating a client at module-load time.
// Never import this into a Client Component.
let client: SupabaseClient | null = null;

export function getSupabaseAdmin(): SupabaseClient {
  if (!client) {
    client = createClient(
      process.env.SUPABASE_URL!,
      process.env.SUPABASE_SERVICE_KEY!,
      { auth: { persistSession: false } },
    );
  }
  return client;
}
