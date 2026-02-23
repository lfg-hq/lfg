import { drizzle } from "drizzle-orm/bun-sqlite";
import { Database as BunDatabase } from "bun:sqlite";
import * as schema from "../db/schema/index.ts";

const sqlite = new BunDatabase("data/lfg.db");
export const db = drizzle(sqlite, { schema });

export type Database = typeof db;
