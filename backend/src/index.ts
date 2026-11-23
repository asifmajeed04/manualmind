import { createApp } from "./app.js";
import { config } from "./config.js";
import { createSupabaseStore } from "./store.js";
import { createAiClient } from "./aiClient.js";

if (!config.supabaseUrl || !config.supabaseServiceRoleKey) {
  console.error("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set (see .env.example)");
  process.exit(1);
}

const app = createApp({
  store: createSupabaseStore(config.supabaseUrl, config.supabaseServiceRoleKey),
  ai: createAiClient(config.aiServiceUrl, config.aiServiceSecret),
});

app.listen(config.port, () => {
  console.log(`Backend listening on http://localhost:${config.port}`);
});
