# Task 1 Brief: Create ListCard Component (Full Accessibility)

**Files:**
- Create: `CRM-Client/src/components/crmwolf/ListCard.vue`

**Interfaces:**
- Consumes: V2 design tokens, Card/Button/Badge from shadcn-vue
- Produces: Generic ListCard component with slots, loading state, focus states

## Design Specs (from list-card.md + accessibility.md)

- Header: title + optional action button
- Content: loading skeleton OR empty state OR list of items
- Item height: min 44px (touch target)
- Item padding: 16px 24px
- Divider: 1px solid #E4ECFC
- Hover: background #F1F5FD
- **Focus: 2px ring rgba(#2563EB, 0.5), offset 2px**
- **Loading: skeleton with shimmer animation**
- **Reduced motion: disable skeleton animation**

## Implementation Steps

- [ ] **Step 1: Create ListCard.vue with full accessibility** (see complete code in plan)
- [ ] **Step 2: Commit ListCard component**

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

This is the first task in a 7-task plan to create a unified ListCard component and refactor all customer detail Sheet panels. The ListCard will be used in:
- ContactsPanel
- OpportunitiesPanel
- ContractsPanel
- PaymentsPanel
- InvoicesPanel
- LicensePanel

The component should be generic with slots-based composition to allow entity-specific content while maintaining visual consistency.