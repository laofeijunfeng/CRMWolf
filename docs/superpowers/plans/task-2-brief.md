# Task 2 Brief: Refactor OpportunitiesPanel (With Aria-Labels)

**Files:**
- Modify: `CRM-Client/src/components/panels/OpportunitiesPanel.vue`

**Interfaces:**
- Consumes: ListCard component (created in Task 1), OpportunityListResponse type
- Produces: OpportunitiesPanel using ListCard with aria-labels on all icon buttons

## Implementation Steps

- [ ] **Step 1: Refactor OpportunitiesPanel to use ListCard** (see complete code in plan)
- [ ] **Step 2: Commit OpportunitiesPanel refactor**

## Key Requirements

1. Replace entire file content with ListCard-based implementation
2. Add aria-label to icon-only button (ExternalLink)
3. Use slots: headerActions, itemMain, itemActions
4. Maintain existing functionality (navigation, status mapping, formatting)

## Global Constraints

- Use V2 design tokens from `variables-v2.scss` exclusively
- Touch targets must be ≥44px height (iOS) / 48px (Android)
- Color contrast must be ≥4.5:1 for normal text, ≥3:1 for large text
- **All interactive elements must have visible focus states** (2px ring, rgba(#2563EB, 0.5))
- **All icon-only buttons must have aria-label**
- **Loading and empty states must have clear visual feedback**
- **Reduced motion support: respect prefers-reduced-motion**
- Follow list-card.md specification for component choice
- TypeScript strict mode - no `any`, use proper typing
- Each task must be independently testable

## Context

This is the second task in a 7-task plan. Task 1 created the ListCard component. Now you're refactoring the first Panel component to use it. The pattern you establish here will be followed by Tasks 3-7 for the other Panels.