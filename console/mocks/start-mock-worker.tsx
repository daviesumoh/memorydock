"use client";

import { useEffect } from "react";

import { startWorker } from "./browser";
import { markWorkerReady } from "./ready";

export default function StartMockWorker() {
  useEffect(() => {
    void startWorker().then(markWorkerReady);
  }, []);
  return null;
}
