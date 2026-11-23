import dotenv from "dotenv";
import path from "node:path";

// The single .env lives in the repo root; also allow backend/.env. In Docker, vars come from env_file.
dotenv.config({ path: [path.resolve(process.cwd(), "../.env"), path.resolve(process.cwd(), ".env")], quiet: true });
