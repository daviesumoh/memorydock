"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useId, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export type FilterField =
  | { name: string; label: string; kind: "text"; placeholder?: string }
  | { name: string; label: string; kind: "select"; options: readonly string[] };

// Radix Select cannot hold an empty value, so "any" stands for no filter.
const ANY = "any";

// Filters live in the URL, so a filtered view can be shared and survives a reload.
export function FilterForm({ fields }: { fields: readonly FilterField[] }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const idPrefix = useId();

  function apply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const next = new URLSearchParams();
    for (const [name, value] of new FormData(event.currentTarget)) {
      if (typeof value === "string" && value.trim() && value !== ANY) next.set(name, value.trim());
    }
    const query = next.toString();
    router.push(query ? `${pathname}?${query}` : pathname);
  }

  return (
    // Keyed by the query string so the uncontrolled fields reset when the URL
    // changes from outside the form (back button, a shared link).
    <form key={searchParams.toString()} onSubmit={apply} className="flex flex-wrap items-end gap-3" aria-label="Filters">
      {fields.map((field) => {
        const id = `${idPrefix}-${field.name}`;
        const current = searchParams.get(field.name) ?? "";
        return (
          <div key={field.name} className="flex flex-col gap-1.5">
            <label htmlFor={id} className="text-sm font-medium">
              {field.label}
            </label>
            {field.kind === "text" ? (
              <Input id={id} name={field.name} defaultValue={current} placeholder={field.placeholder} className="w-44" />
            ) : (
              <Select name={field.name} defaultValue={current || ANY}>
                <SelectTrigger id={id} className="w-40">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ANY}>Any</SelectItem>
                  {field.options.map((option) => (
                    <SelectItem key={option} value={option}>
                      {option.replace("_", " ")}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>
        );
      })}
      <Button type="submit" variant="secondary">
        Apply
      </Button>
    </form>
  );
}

// Reads the current filters back out of the URL for the query hooks.
export function useFilterValues(fields: readonly FilterField[]): Record<string, string> {
  const searchParams = useSearchParams();
  const values: Record<string, string> = {};
  for (const { name } of fields) {
    const value = searchParams.get(name);
    if (value) values[name] = value;
  }
  return values;
}
