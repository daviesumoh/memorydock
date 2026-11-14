// Default deny. Forbids first, then the permits that grant access.

// Kill switch and session state apply to every action.
@id("org-kill-switch")
forbid (principal, action, resource)
when { principal.org.killSwitch };

@id("session-not-live")
forbid (principal, action, resource)
when { ["revoked", "ended"].contains(principal.status) };

// Paused sessions can still read.
@id("session-not-active-no-writes")
forbid (principal, action in Memorydock::Action::"WriteActions", resource)
when { principal.status != "active" };

// Memory
@id("memory-read-in-scope")
permit (principal, action == Memorydock::Action::"memory.read", resource)
when { principal.user.readableScopes.contains(resource.scopeKey) && resource.status != "proposed" };

@id("memory-write-in-scope")
permit (
  principal,
  action in [
    Memorydock::Action::"memory.write",
    Memorydock::Action::"memory.correct",
    Memorydock::Action::"memory.flag",
    Memorydock::Action::"memory.forget",
    Memorydock::Action::"memory.share"
  ],
  resource
)
when { principal.user.writableScopes.contains(resource.scopeKey) };

@id("share-target-in-scope")
forbid (principal, action == Memorydock::Action::"memory.share", resource)
unless { context has targetScopeKey && principal.user.writableScopes.contains(context.targetScopeKey) };

@id("shared-forget-needs-reason")
forbid (principal, action == Memorydock::Action::"memory.forget", resource)
when { resource.scopeLevel != "user" }
unless { context has reason && context.reason != "" };

@id("category-confined-to-personal")
forbid (
  principal,
  action in [Memorydock::Action::"memory.write", Memorydock::Action::"memory.share"],
  resource
)
when {
  resource.confined &&
  (resource.scopeLevel != "user" || (context has targetLevel && context.targetLevel != "user"))
};

@id("category-max-scope")
forbid (
  principal,
  action in [Memorydock::Action::"memory.write", Memorydock::Action::"memory.share"],
  resource
)
when {
  resource.scopeRank > resource.categoryMaxRank ||
  (context has targetRank && context.targetRank > resource.categoryMaxRank)
};

// Capture: a session captures into itself only.
@id("capture-own-session")
permit (principal, action == Memorydock::Action::"turn.capture", resource)
when { resource == principal };

// Review items belong to one user.
@id("review-own-items")
permit (
  principal,
  action in [Memorydock::Action::"review.read", Memorydock::Action::"review.decide"],
  resource
)
when { resource.ownerUser == principal.user };

// Approvals
@id("no-self-approval")
forbid (principal, action == Memorydock::Action::"approval.decide", resource)
when { resource.requesterUser == principal.user };

@id("approver-decides")
permit (principal, action == Memorydock::Action::"approval.decide", resource)
when { resource.approvers.contains(principal.user) };

@id("approval-read-involved")
permit (principal, action == Memorydock::Action::"approval.read", resource)
when { resource.requesterUser == principal.user || resource.approvers.contains(principal.user) };

// Project work: files, leases, tasks and external actions.
@id("project-members-files")
permit (
  principal,
  action in [Memorydock::Action::"file.edit", Memorydock::Action::"bash.exec"],
  resource
)
when { resource.project.members.contains(principal.user) };

@id("project-members-leases")
permit (
  principal,
  action in [
    Memorydock::Action::"lease.read",
    Memorydock::Action::"lease.acquire",
    Memorydock::Action::"lease.release",
    Memorydock::Action::"lease.request",
    Memorydock::Action::"lease.override"
  ],
  resource
)
when { resource.project.members.contains(principal.user) };

@id("project-members-tasks")
permit (
  principal,
  action in [
    Memorydock::Action::"task.read",
    Memorydock::Action::"task.create",
    Memorydock::Action::"task.claim",
    Memorydock::Action::"task.update",
    Memorydock::Action::"task.handoff",
    Memorydock::Action::"task.cancel",
    Memorydock::Action::"task.rollback"
  ],
  resource
)
when { resource.project.members.contains(principal.user) };

@id("project-members-external")
permit (principal, action in Memorydock::Action::"ExternalActions", resource)
when { resource.project.members.contains(principal.user) };

@id("file-edit-lease-conflict")
forbid (principal, action == Memorydock::Action::"file.edit", resource)
when { resource.leaseConflict };

@id("merge-needs-maintainer")
forbid (principal, action == Memorydock::Action::"github.merge_pr", resource)
unless { resource.project.maintainers.contains(principal.user) };

// Audit and policy views: members read their org's (rows are filtered by visibility in code);
// only org admins verify the chain.
@id("audit-read-own-org")
permit (
  principal,
  action in [Memorydock::Action::"audit.read", Memorydock::Action::"policy.read"],
  resource
)
when { resource.org == principal.org };

@id("audit-admin-verify")
permit (principal, action == Memorydock::Action::"audit.verify", resource)
when { principal.user.isOrgAdmin && resource.org == principal.org };

// Sessions: the owner, or an org admin of the same org, pauses, resumes or revokes.
@id("session-control-owner-or-admin")
permit (
  principal,
  action in [
    Memorydock::Action::"session.pause",
    Memorydock::Action::"session.resume",
    Memorydock::Action::"session.revoke"
  ],
  resource
)
when {
  resource.user == principal.user ||
  (principal.user.isOrgAdmin && resource.org == principal.org)
};
