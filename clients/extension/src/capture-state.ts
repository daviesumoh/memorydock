// Whether a ChatGPT tab may capture. Capture is off unless every check passes,
// and the checks run in a fixed order so the reason shown is always the first
// thing in the way.

export interface PageFacts {
  // The DOM contract matched nothing on a page with content for too long.
  drift: boolean;
  temporaryChat: boolean;
  conversationId: string | null;
  // ChatGPT Project the conversation belongs to, if any.
  projectId: string | null;
}

export interface UserFacts {
  signedIn: boolean;
  // Projects the user ticked for capture.
  tickedProjects: ReadonlySet<string>;
  // Projects with a saved mapping to a memorydock scope.
  mappedProjects: ReadonlySet<string>;
}

export type CaptureBlock =
  | "drift"
  | "temporary_chat"
  | "not_signed_in"
  | "no_conversation"
  | "not_in_project"
  | "project_not_enabled";

export type CaptureState = { capturing: true; projectId: string } | { capturing: false; reason: CaptureBlock };

export function captureState(page: PageFacts, user: UserFacts): CaptureState {
  if (page.drift) return { capturing: false, reason: "drift" };
  if (page.temporaryChat) return { capturing: false, reason: "temporary_chat" };
  if (!user.signedIn) return { capturing: false, reason: "not_signed_in" };
  if (!page.conversationId) return { capturing: false, reason: "no_conversation" };
  // Chats outside a ChatGPT Project are never captured.
  if (!page.projectId) return { capturing: false, reason: "not_in_project" };
  if (!user.tickedProjects.has(page.projectId) || !user.mappedProjects.has(page.projectId)) {
    return { capturing: false, reason: "project_not_enabled" };
  }
  return { capturing: true, projectId: page.projectId };
}
