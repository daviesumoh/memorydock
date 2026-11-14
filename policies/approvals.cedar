// Evaluated only after authz allows. A permit here means a human must approve first.

@id("approve-lease-override")
permit (principal, action == Memorydock::Action::"lease.override", resource);

@id("approve-org-write")
permit (principal, action == Memorydock::Action::"memory.write", resource)
when { resource.scopeLevel == "org" };

@id("approve-org-share")
permit (principal, action == Memorydock::Action::"memory.share", resource)
when { context has targetLevel && context.targetLevel == "org" };

@id("approve-pr-comment")
permit (principal, action == Memorydock::Action::"github.comment_pr", resource);

@id("approve-protected-merge")
permit (principal, action == Memorydock::Action::"github.merge_pr", resource)
when { resource.isProtected };
