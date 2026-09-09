"use client";

import { useCallback, useState } from "react";
import { useDropzone, FileRejection } from "react-dropzone";
import { useRouter } from "next/navigation";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080";

type State =
  | { status: "idle" }
  | { status: "uploading"; progress: number }
  | { status: "error"; message: string };

function mapDropzoneRejection(rejection: FileRejection): string {
  for (const err of rejection.errors) {
    if (err.code === "file-too-large") return "File too large (25 MB max)";
    if (err.code === "file-invalid-type") return "Only PDF files are accepted";
  }
  return "File was rejected. Please try again.";
}

export default function UploadPage() {
  const router = useRouter();
  const [state, setState] = useState<State>({ status: "idle" });

  const uploadFile = useCallback(
    (file: File) => {
      setState({ status: "uploading", progress: 0 });

      const xhr = new XMLHttpRequest();
      const formData = new FormData();
      formData.append("file", file);

      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
          const pct = Math.round((e.loaded / e.total) * 100);
          setState({ status: "uploading", progress: pct });
        }
      };

      xhr.onload = async () => {
        if (xhr.status === 201) {
          try {
            const data = JSON.parse(xhr.responseText) as { script_id: string };
            router.push("/scripts/" + data.script_id);
          } catch {
            setState({ status: "error", message: "Unexpected response from server." });
          }
          return;
        }

        if (xhr.status === 413) {
          setState({ status: "error", message: "File too large (25 MB max)" });
          return;
        }
        if (xhr.status === 415) {
          setState({ status: "error", message: "Only PDF files are accepted" });
          return;
        }
        if (xhr.status === 422) {
          try {
            const body = JSON.parse(xhr.responseText) as { code?: string };
            if (body.code === "NO_TEXT_LAYER") {
              setState({
                status: "error",
                message:
                  "This PDF has no text layer. Re-export or use a text-based PDF.",
              });
              return;
            }
          } catch {
            // fall through to generic error
          }
        }

        setState({
          status: "error",
          message: `Upload failed (HTTP ${xhr.status}). Please try again.`,
        });
      };

      xhr.onerror = () => {
        setState({ status: "error", message: "Network error. Please try again." });
      };

      xhr.open("POST", `${API_BASE}/api/scripts`);
      xhr.send(formData);
    },
    [router]
  );

  const onDrop = useCallback(
    (accepted: File[], rejections: FileRejection[]) => {
      if (rejections.length > 0) {
        setState({ status: "error", message: mapDropzoneRejection(rejections[0]) });
        return;
      }
      if (accepted.length > 0) {
        uploadFile(accepted[0]);
      }
    },
    [uploadFile]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { "application/pdf": [".pdf"] },
    maxSize: 25 * 1024 * 1024,
    multiple: false,
    disabled: state.status === "uploading",
  });

  const isUploading = state.status === "uploading";

  return (
    <div className="flex flex-1 flex-col items-center justify-center bg-slate-950 px-4">
      <div className="w-full max-w-lg">
        <h1 className="mb-2 text-center text-2xl font-semibold text-slate-100">
          Screenplay Clearance
        </h1>
        <p className="mb-4 text-center text-sm text-slate-400">
          Upload a PDF screenplay to begin clearance analysis.
        </p>

        {/*
          Said plainly rather than discovered as a failure. The hosted demo
          runs on Gemini's free tier: 20 requests a day, and a run costs four
          of them, shared across everyone using this link. Research is cached
          per entity so a second script that mentions Coca-Cola does not pay
          for it again, but extraction and assessment are context-specific
          and never cached, so four per run is the floor.
        */}
        <p className="mb-8 rounded-lg border border-amber-500/30 bg-amber-500/5
                      px-4 py-3 text-center text-xs leading-relaxed text-slate-400">
          This demo shares a free-tier quota of about five runs a day. If a run
          fails on quota, the completed example in the sidebar shows the full
          findings, the sources and the exported report.
        </p>

        <div
          {...getRootProps()}
          className={[
            "flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-8 py-16 transition-colors",
            isDragActive
              ? "border-blue-500 bg-slate-900"
              : isUploading
              ? "cursor-not-allowed border-slate-700 bg-slate-900"
              : "border-slate-700 bg-white hover:border-blue-400 hover:bg-slate-900",
          ].join(" ")}
        >
          <input {...getInputProps()} />

          {isUploading ? (
            <div className="w-full">
              <p className="mb-3 text-center text-sm font-medium text-slate-300">
                Uploading… {state.progress}%
              </p>
              <div className="h-2 w-full overflow-hidden rounded-full bg-slate-800">
                <div
                  className="h-full rounded-full bg-slate-9000 transition-all duration-150"
                  style={{ width: `${state.progress}%` }}
                />
              </div>
            </div>
          ) : (
            <>
              <svg
                className="mb-4 h-10 w-10 text-slate-500"
                fill="none"
                stroke="currentColor"
                strokeWidth={1.5}
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5"
                />
              </svg>
              <p className="text-sm font-medium text-slate-200">
                {isDragActive ? "Drop the PDF here" : "Drag & drop a PDF, or click to select"}
              </p>
              <p className="mt-1 text-xs text-slate-500">PDF only · 25 MB max</p>
            </>
          )}
        </div>

        {state.status === "error" && (
          <p className="mt-4 text-center text-sm text-accent-red" role="alert">
            {state.message}
          </p>
        )}
      </div>
    </div>
  );
}
