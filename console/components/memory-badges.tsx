import { Badge } from "@/components/ui/badge";
import type { Schemas } from "@/lib/api/client";

// The word is the signal; colour only reinforces it.
const STATUS_VARIANT: Record<Schemas["MemoryOut"]["status"], "default" | "secondary" | "destructive" | "outline"> = {
  active: "default",
  proposed: "secondary",
  superseded: "outline",
  conflict: "destructive",
  disputed: "destructive",
  expired: "outline",
  forgotten: "outline",
};

export function StatusBadge({ status }: { status: Schemas["MemoryOut"]["status"] }) {
  return <Badge variant={STATUS_VARIANT[status]}>{status}</Badge>;
}

export function TypeBadge({ type }: { type: Schemas["MemoryOut"]["type"] }) {
  return <Badge variant="secondary">{type.replace("_", " ")}</Badge>;
}

const EFFECT_VARIANT: Record<Schemas["AuditDecision"]["effect"], "default" | "secondary" | "destructive" | "outline"> = {
  allow: "default",
  deny: "destructive",
  approval_required: "secondary",
  "n/a": "outline",
};

export function EffectBadge({ effect }: { effect: Schemas["AuditDecision"]["effect"] }) {
  return <Badge variant={EFFECT_VARIANT[effect]}>{effect.replace("_", " ")}</Badge>;
}
