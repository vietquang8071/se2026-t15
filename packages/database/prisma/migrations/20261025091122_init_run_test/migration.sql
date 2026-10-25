-- CreateTable
CREATE TABLE "Meeting" (
    "id" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "anchorDate" DATE NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "Meeting_pkey" PRIMARY KEY ("id")
);
