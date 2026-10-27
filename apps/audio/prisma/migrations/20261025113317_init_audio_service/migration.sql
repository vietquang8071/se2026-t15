-- CreateTable
CREATE TABLE "AudioAsset" (
    "id" UUID NOT NULL,
    "originalName" TEXT NOT NULL,
    "sourceKey" TEXT NOT NULL,
    "metadata" JSONB NOT NULL,
    "retentionDays" INTEGER NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "expiresAt" TIMESTAMP(3) NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'uploaded',
    "transcript" JSONB,

    CONSTRAINT "AudioAsset_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "AudioJob" (
    "id" UUID NOT NULL,
    "audioId" UUID NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'queued',
    "stage" TEXT NOT NULL DEFAULT 'queued',
    "progress" INTEGER NOT NULL DEFAULT 0,
    "attempts" INTEGER NOT NULL DEFAULT 0,
    "providerCalls" INTEGER NOT NULL DEFAULT 0,
    "errorCode" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,
    "checkpoints" JSONB NOT NULL DEFAULT '{}',

    CONSTRAINT "AudioJob_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "AudioAsset_expiresAt_idx" ON "AudioAsset"("expiresAt");

-- CreateIndex
CREATE INDEX "AudioJob_status_createdAt_idx" ON "AudioJob"("status", "createdAt");

-- CreateIndex
CREATE UNIQUE INDEX "AudioJob_audioId_key" ON "AudioJob"("audioId");

-- AddForeignKey
ALTER TABLE "AudioJob" ADD CONSTRAINT "AudioJob_audioId_fkey" FOREIGN KEY ("audioId") REFERENCES "AudioAsset"("id") ON DELETE CASCADE ON UPDATE CASCADE;
