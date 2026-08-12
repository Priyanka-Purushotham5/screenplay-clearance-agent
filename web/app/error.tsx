"use client";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center min-h-full gap-4 p-8">
      <p className="text-red-600">{error.message}</p>
      <button
        onClick={reset}
        className="px-4 py-2 rounded bg-gray-100 hover:bg-gray-200 text-sm"
      >
        Try again
      </button>
    </div>
  );
}
