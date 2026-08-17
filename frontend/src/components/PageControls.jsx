import {
  Pagination, PaginationContent, PaginationItem,
  PaginationPrevious, PaginationNext,
} from '@/components/ui/pagination';

// Shared prev/(page X of Y)/next controls for any client-side-paginated
// admin list (users table, pending recommendations, recent agent actions,
// ...). Renders nothing when there's only one page, so callers don't need
// to guard on totalPages themselves.
export default function PageControls({ page, totalPages, onChange }) {
  if (totalPages <= 1) return null;
  return (
    <Pagination className="mt-3">
      <PaginationContent>
        <PaginationItem>
          <PaginationPrevious
            href="#"
            aria-disabled={page === 1}
            className={page === 1 ? 'pointer-events-none opacity-40' : undefined}
            onClick={(e) => { e.preventDefault(); if (page > 1) onChange(page - 1); }}
          />
        </PaginationItem>
        <PaginationItem>
          <span className="px-3 text-xs text-slate-500 dark:text-slate-400 whitespace-nowrap">
            Page {page} of {totalPages}
          </span>
        </PaginationItem>
        <PaginationItem>
          <PaginationNext
            href="#"
            aria-disabled={page === totalPages}
            className={page === totalPages ? 'pointer-events-none opacity-40' : undefined}
            onClick={(e) => { e.preventDefault(); if (page < totalPages) onChange(page + 1); }}
          />
        </PaginationItem>
      </PaginationContent>
    </Pagination>
  );
}
