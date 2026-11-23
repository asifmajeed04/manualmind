import "./env.js";

export const config = {
  port: Number(process.env.PORT ?? 3001),
  supabaseUrl: process.env.SUPABASE_URL ?? "",
  supabaseServiceRoleKey: process.env.SUPABASE_SERVICE_ROLE_KEY ?? "",
  aiServiceUrl: process.env.AI_SERVICE_URL ?? "http://localhost:8000",
  aiServiceSecret: process.env.AI_SERVICE_SECRET ?? "",
  corsOrigin: process.env.CORS_ORIGIN ?? "http://localhost:5173",
};
