// Verifies the milestone-1 setup against your Supabase project.
// Run: cd backend && npm run check-setup
import "../src/env.js";
import { createClient } from "@supabase/supabase-js";

const env = process.env;
let failures = 0;
const ok = (msg: string) => console.log(`  ✔ ${msg}`);
const fail = (msg: string, hint?: string) => {
  failures++;
  console.log(`  ✘ ${msg}${hint ? `\n      -> ${hint}` : ""}`);
};

async function main() {
  console.log("\n1. Environment variables");
  for (const k of ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_ANON_KEY", "AI_SERVICE_SECRET"]) {
    env[k] ? ok(`${k} is set`) : fail(`${k} is empty`, "fill it in the root .env");
  }
  const url = env.SUPABASE_URL ?? "";
  if (url && !/^https:\/\/[a-z0-9]+\.supabase\.co\/?$/.test(url))
    fail("SUPABASE_URL looks unusual", "expected https://<ref>.supabase.co");
  for (const k of ["SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_ANON_KEY"]) {
    if (env[k]?.includes("/")) fail(`${k} contains '/'`, "remove the label pasted in front of the key");
  }
  if (!env.OPENAI_API_KEY) console.log("  - OPENAI_API_KEY empty (fine for now, needed from milestone 3)");
  if (!url || !env.SUPABASE_SERVICE_ROLE_KEY || !env.SUPABASE_ANON_KEY) return;

  const admin = createClient(url, env.SUPABASE_SERVICE_ROLE_KEY!, { auth: { persistSession: false } });
  const anon = createClient(url, env.SUPABASE_ANON_KEY!, { auth: { persistSession: false } });

  console.log("\n2. Tables (service role)");
  for (const t of ["documents", "chunks", "chat_messages"]) {
    const { error } = await admin.from(t).select("id", { head: true, count: "exact" });
    error ? fail(`table ${t}: ${error.message}`, "run the migration SQL in the SQL editor") : ok(`table ${t} exists`);
  }

  console.log("\n3. Storage");
  const { data: bucket, error: bErr } = await admin.storage.getBucket("documents");
  if (bErr || !bucket) fail(`bucket 'documents': ${bErr?.message ?? "missing"}`, "run the migration SQL");
  else bucket.public ? fail("bucket 'documents' is PUBLIC", "make it private") : ok("private bucket 'documents' exists");

  console.log("\n4. Search functions (RPC)");
  const zeroUser = "00000000-0000-0000-0000-000000000000";
  const kw = await admin.rpc("match_chunks_keyword", { query_text: "E42", p_user_id: zeroUser, k: 5 });
  kw.error ? fail(`match_chunks_keyword: ${kw.error.message}`) : ok("match_chunks_keyword works");
  const vec = await admin.rpc("match_chunks_vector", {
    query_embedding: JSON.stringify(Array(1536).fill(0.01)),
    p_user_id: zeroUser,
    k: 5,
  });
  vec.error ? fail(`match_chunks_vector: ${vec.error.message}`) : ok("match_chunks_vector works (pgvector OK)");

  console.log("\n5. Security (anon / browser key)");
  const anonRead = await anon.from("documents").select("id");
  if (anonRead.error) fail(`anon read errored: ${anonRead.error.message}`);
  else anonRead.data.length === 0 ? ok("RLS hides documents from anonymous users") : fail("anon can read documents!", "check RLS");
  const anonRpc = await anon.rpc("match_chunks_keyword", { query_text: "x", p_user_id: zeroUser, k: 1 });
  anonRpc.error ? ok("anon cannot call search functions") : fail("anon CAN call search functions", "re-run the revoke lines");
}

main()
  .catch((e) => fail(`unexpected error: ${e.message}`))
  .finally(() => {
    console.log(failures ? `\n${failures} check(s) failed.\n` : "\nAll checks passed ✔\n");
    process.exitCode = failures ? 1 : 0;
  });
