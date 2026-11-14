import { Badge } from "@/components/ui/badge";
import type { Schemas } from "@/lib/api/client";

// The word is the signal; colour only reinforces it.
const STATUS_VARIANT: Record<Schemas["MemoryStatus"], "default" | "secondary" | "destructive" | "outline"> = {
  active: "default",
  proposed: "secondary",
  superseded: "outline",
  conflict: "destructive",
  disputed: "destructive",
  expired: "outline",
  forgotten: "outline",
};

export function StatusBadge({ status }: { status: Schemas["MemoryStatus"] }) {
  return <Badge variant={STATUS_VARIANT[status]}>{status}</Badge>;
}

export function TypeBadge({ type }: { type: Schemas["MemoryType"] }) {
  return <Badge variant="secondary">{type.replace("_", " ")}</Badge>;
}

const EFFECT_VARIANT: Record<Schemas["AuditEffect"], "default" | "secondary" | "destructive" | "outline"> = {
  allow: "default",
  deny: "destructive",
  approval_required: "secondary",
  "n/a": "outline",
};

export function EffectBadge({ effect }: { effect: Schemas["AuditEffect"] }) {
  return <Badge variant={EFFECT_VARIANT[effect]}>{effect.replace("_", " ")}</Badge>;
}
