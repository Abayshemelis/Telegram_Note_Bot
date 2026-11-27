export function Toast({ error, notice, onDismiss }) {
  if (!error && !notice) return null;

  return (
    <div className={error ? "toast toast-error" : "toast toast-success"}>
      {error || notice}
      <button onClick={onDismiss} aria-label="Dismiss">×</button>
    </div>
  );
}
