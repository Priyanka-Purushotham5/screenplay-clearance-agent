import runMeta from "@/lib/fixtures/run-meta.json";

export async function GET() {
  return Response.json(runMeta);
}
