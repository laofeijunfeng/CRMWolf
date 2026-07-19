/**
 * CRMWolf Design System Components
 * UI/UX Pro Max compliant primitives
 */

// Touch-optimized components
export { default as TouchInput } from './TouchInput.vue'
export { default as TouchCard } from './TouchCard.vue'

// Navigation components (§9 HIGH Priority)
export { default as BottomNav } from './BottomNav.vue'
export { default as BottomNavItem } from './BottomNavItem.vue'
export { default as BottomNavOverflow } from './BottomNavOverflow.vue'
export { default as ContextTabs } from './ContextTabs.vue'
export { default as TopBarTabs } from './TopBarTabs.vue'

// Data display components
export { default as DataTable } from './DataTable.vue'
export { default as FilterPanel } from './FilterPanel.vue'
export { default as FileAttachment } from './FileAttachment.vue'
export { default as ListCard } from './ListCard.vue'
export { default as ListFilterPopover } from './ListFilterPopover.vue'
export { default as ListSortPopover } from './ListSortPopover.vue'
export { default as MultiSelect } from './MultiSelect.vue'
export { default as TableToolbarButton } from './TableToolbarButton.vue'
export { default as TableToolbarBuilderPanel } from './TableToolbarBuilderPanel.vue'
export { default as TableRowActions } from './TableRowActions.vue'
export { default as StatusBadge } from '../StatusBadge.vue'

// Export types
export type { ActionConfig } from './TableRowActions.vue'
export type { ListFilterCondition, ListFilterField } from './listFilterTypes'
export type { ListSortCondition, ListSortField } from './listSortTypes'

// Feedback components (§8 MEDIUM Priority)
export { default as LoadingSkeleton } from './LoadingSkeleton.vue'
export { default as SearchCard } from './SearchCard.vue'
export { default as ConfirmDialog } from './ConfirmDialog.vue'

// Re-export shadcn-vue primitives for convenience
// Core components
export { Button } from '@/components/ui/button'
export { Input } from '@/components/ui/input'
export { Textarea } from '@/components/ui/textarea'
export { Label } from '@/components/ui/label'

// Layout & Container
export { Card, CardHeader, CardContent, CardFooter } from '@/components/ui/card'
export { Separator } from '@/components/ui/separator'
export { ScrollArea } from '@/components/ui/scroll-area'
export { AspectRatio } from '@/components/ui/aspect-ratio'

// Navigation
export { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
export { Breadcrumb, BreadcrumbItem, BreadcrumbLink, BreadcrumbSeparator } from '@/components/ui/breadcrumb'
export { NavigationMenu, NavigationMenuItem, NavigationMenuLink } from '@/components/ui/navigation-menu'

// Data Entry
export { Checkbox } from '@/components/ui/checkbox'
export { Switch } from '@/components/ui/switch'
export { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
export { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
export { Combobox } from '@/components/ui/combobox'
export { Slider } from '@/components/ui/slider'

// Feedback & Status
export { Badge } from '@/components/ui/badge'
export { Progress } from '@/components/ui/progress'
export { Skeleton } from '@/components/ui/skeleton'
export { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar'
export { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
export { Toast, toast } from '@/components/ui/toast'

// Overlays & Modals
export { Dialog, DialogContent, DialogHeader, DialogFooter, DialogTitle, DialogDescription } from '@/components/ui/dialog'
export { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogHeader, AlertDialogTitle, AlertDialogDescription } from '@/components/ui/alert-dialog'
export { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, DropdownMenuSeparator } from '@/components/ui/dropdown-menu'
export { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
export { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from '@/components/ui/sheet'
export { Drawer, DrawerContent, DrawerHeader, DrawerTitle, DrawerDescription } from '@/components/ui/drawer'
export { Tooltip, TooltipContent, TooltipTrigger, TooltipProvider } from '@/components/ui/tooltip'
export { HoverCard, HoverCardContent, HoverCardTrigger } from '@/components/ui/hover-card'

// Commands & Menus
export { Command, CommandInput, CommandList, CommandItem, CommandGroup, CommandEmpty } from '@/components/ui/command'
export { ContextMenu, ContextMenuContent, ContextMenuItem, ContextMenuTrigger } from '@/components/ui/context-menu'
export { Menubar, MenubarContent, MenubarItem, MenubarTrigger } from '@/components/ui/menubar'

// Tables
export { Table, TableHeader, TableRow, TableCell } from '@/components/ui/table'

// Form
export { Form } from '@/components/ui/form'

// Accordion & Collapsible
export { Accordion, AccordionItem, AccordionTrigger, AccordionContent } from '@/components/ui/accordion'
export { Collapsible, CollapsibleTrigger, CollapsibleContent } from '@/components/ui/collapsible'

// Carousel
export { Carousel, CarouselContent, CarouselItem, CarouselNext, CarouselPrevious } from '@/components/ui/carousel'

// Pagination
export { Pagination } from '@/components/ui/pagination'
