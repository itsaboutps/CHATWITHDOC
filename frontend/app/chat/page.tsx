// Deprecated legacy chat route. All interactions now live at '/'.
// Keeping a placeholder component (returning null) so that if a user navigates
// to /chat they simply get redirected logic (handled elsewhere) or nothing rendered.
// This avoids build errors from multiple default exports while honoring the
// single-page app requirement.
export default function ChatPlaceholder(){ return null; }
