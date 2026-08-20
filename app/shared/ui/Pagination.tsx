type PaginationProps = {
  page: number;
  pages: number;
  total: number;
  onChange: (page: number) => void;
};

/** A single navigation interface for all local, paginated collections. */
export function Pagination({ page, pages, total, onChange }: PaginationProps) {
  return <div className="pagination"><small>共 {total} 条 · 第 {page} / {pages} 页</small><div><button disabled={page <= 1} onClick={() => onChange(page - 1)}>上一页</button><button disabled={page >= pages} onClick={() => onChange(page + 1)}>下一页</button></div></div>;
}
