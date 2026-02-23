import { createAnthropic } from "@ai-sdk/anthropic";
import { createOpenAI } from "@ai-sdk/openai";
import { createGoogleGenerativeAI } from "@ai-sdk/google";
import { env } from "../config/env.ts";
import modelsConfig from "../config/llm-models.json" with { type: "json" };
import type { LanguageModel } from "ai";

export type ProviderName = "anthropic" | "openai" | "google";

interface ModelEntry {
  key: string;
  provider_model: string;
  requires_pro: boolean;
}

interface ProviderConfig {
  label: string;
  default_model: string;
  models: ModelEntry[];
}

// Flat map: modelKey → { providerName, providerModel }
const modelIndex = new Map<string, { provider: ProviderName; model: string }>();
for (const [providerName, cfg] of Object.entries(
  modelsConfig.providers as Record<string, ProviderConfig>
)) {
  for (const m of cfg.models) {
    modelIndex.set(m.key, {
      provider: providerName as ProviderName,
      model: m.provider_model,
    });
  }
}

export const DEFAULT_MODEL_KEY = modelsConfig.default_model;

/**
 * Get a LanguageModelV1 instance from a model key (e.g. "claude_4.5_sonnet").
 * Optionally supply per-user API keys; falls back to env vars.
 */
export function getModel(
  modelKey: string,
  userApiKeys?: { anthropic?: string; openai?: string; google?: string }
): LanguageModel {
  const entry = modelIndex.get(modelKey);
  if (!entry) {
    throw new Error(`Unknown model key: ${modelKey}`);
  }

  const { provider, model } = entry;

  switch (provider) {
    case "anthropic": {
      const apiKey = userApiKeys?.anthropic || env.ANTHROPIC_API_KEY;
      if (!apiKey) throw new Error("No Anthropic API key configured");
      const anthropic = createAnthropic({ apiKey });
      return anthropic(model);
    }
    case "openai": {
      const apiKey = userApiKeys?.openai || env.OPENAI_API_KEY;
      if (!apiKey) throw new Error("No OpenAI API key configured");
      const openai = createOpenAI({ apiKey });
      return openai(model);
    }
    case "google": {
      const apiKey = userApiKeys?.google || env.GOOGLE_AI_API_KEY;
      if (!apiKey) throw new Error("No Google AI API key configured");
      const google = createGoogleGenerativeAI({ apiKey });
      return google(model);
    }
    default:
      throw new Error(`Unknown provider: ${provider}`);
  }
}

/** List all available models with metadata */
export function listModels() {
  const result: Array<{
    key: string;
    provider: ProviderName;
    providerModel: string;
    requiresPro: boolean;
    providerLabel: string;
  }> = [];

  for (const [providerName, cfg] of Object.entries(
    modelsConfig.providers as Record<string, ProviderConfig>
  )) {
    for (const m of cfg.models) {
      result.push({
        key: m.key,
        provider: providerName as ProviderName,
        providerModel: m.provider_model,
        requiresPro: m.requires_pro,
        providerLabel: cfg.label,
      });
    }
  }
  return result;
}
