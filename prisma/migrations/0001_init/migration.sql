-- Initial tables for AI Debug Copilot persistence.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE "DebugSession" (
  "id" UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  "userId" VARCHAR(255),
  "createdAt" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  "updatedAt" TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE "Message" (
  "id" UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  "sessionId" UUID NOT NULL REFERENCES "DebugSession" ("id") ON DELETE CASCADE,
  "role" VARCHAR(20) NOT NULL,
  "language" VARCHAR(50),
  "errorText" TEXT,
  "codeSnippet" TEXT,
  "assistantJson" JSONB,
  "rawModelOutput" TEXT,
  "createdAt" TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE "DebugResult" (
  "id" UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  "messageId" UUID NOT NULL UNIQUE REFERENCES "Message" ("id") ON DELETE CASCADE,
  "errorType" TEXT NOT NULL,
  "rootCause" JSONB NOT NULL,
  "fixSuggestions" JSONB NOT NULL,
  "prevention" JSONB NOT NULL,
  "rawModelOutput" TEXT NOT NULL,
  "modelName" TEXT NOT NULL,
  "promptVersion" TEXT NOT NULL,
  "createdAt" TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX "DebugSession_updatedAt_idx" ON "DebugSession" ("updatedAt");
CREATE INDEX "Message_sessionId_idx" ON "Message" ("sessionId");
CREATE INDEX "Message_createdAt_idx" ON "Message" ("createdAt");
