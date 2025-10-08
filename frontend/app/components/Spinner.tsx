export function Spinner({ size = 20, className = '' }: { size?: number; className?: string }) {
  return (
    <span
      aria-label="loading"
      className={`inline-block animate-spin rounded-full border-2 border-current border-r-transparent align-middle ${className}`}
      style={{ width: size, height: size }}
    />
  );
}
